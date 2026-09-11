import gc
import os
import sys
import json
import time
import random
import tempfile
import glob
import traceback
import queue
import threading
import numpy as np
import subprocess
import psutil
import soundfile as sf
import torch
from PIL import Image

# ── Bootstrap Wan2GP ──
WAN2GP_DIR = os.path.abspath("Wan2GP")
if WAN2GP_DIR not in sys.path:
    sys.path.insert(0, WAN2GP_DIR)
os.chdir(WAN2GP_DIR)

OUTPUTS_DIR = os.path.abspath(os.path.join(WAN2GP_DIR, "outputs"))
os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs("/kaggle/working/outputs", exist_ok=True)

# Enable PyTorch & cuDNN fast inference optimizations
torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True
torch.backends.cudnn.benchmark = True
torch.backends.cuda.enable_flash_sdp(False)
torch.backends.cuda.enable_mem_efficient_sdp(True)
torch.backends.cuda.enable_mem_efficient_sdp(True)
torch.backends.cuda.enable_mem_efficient_sdp(True)
torch.backends.cuda.enable_math_sdp(True)

# Clean any leftover lock files from previous runs
for lock_name in ['startup.lock', 'wgp.lock']:
    lock_path = os.path.join(WAN2GP_DIR, lock_name)
    if os.path.exists(lock_path):
        try:
            os.remove(lock_path)
        except Exception:
            pass

# Backward-compatibility patch for HfFolder in huggingface_hub
try:
    import huggingface_hub.utils as hf_utils
    if not hasattr(hf_utils, 'HfFolder'):
        class HfFolder:
            @staticmethod
            def get_token():
                import os
                try:
                    from huggingface_hub import get_token
                    return get_token() or os.environ.get('HF_TOKEN')
                except Exception:
                    return os.environ.get('HF_TOKEN')
            @staticmethod
            def save_token(token):
                pass
        setattr(hf_utils, 'HfFolder', HfFolder)
        if 'huggingface_hub.utils' in sys.modules:
            setattr(sys.modules['huggingface_hub.utils'], 'HfFolder', HfFolder)
except Exception:
    pass

# Patch ltx2.py in Wan2GP to disable requires_grad on empty models so int8 weights load cleanly
ltx2_file = os.path.join(WAN2GP_DIR, "models", "ltx2", "ltx2.py")
if os.path.isfile(ltx2_file):
    with open(ltx2_file, "r", encoding="utf-8") as f:
        ltx2_code = f.read()
    if 'def _load_component(model, path, sd_ops=None, postprocess=None, ignore_unused_weights=False):\n            if postprocess is None and sd_ops is not None:' in ltx2_code:
        ltx2_code = ltx2_code.replace(
            'def _load_component(model, path, sd_ops=None, postprocess=None, ignore_unused_weights=False):\n            if postprocess is None and sd_ops is not None:',
            'def _load_component(model, path, sd_ops=None, postprocess=None, ignore_unused_weights=False):\n            model.requires_grad_(False)\n            if postprocess is None and sd_ops is not None:'
        )
        with open(ltx2_file, "w", encoding="utf-8") as f:
            f.write(ltx2_code)

# Patch distilled.py in Wan2GP to use model dtype instead of hardcoded bfloat16 (enables fast FP16 on T4)
distilled_file = os.path.join(WAN2GP_DIR, "models", "ltx2", "ltx_pipelines", "distilled.py")
if os.path.isfile(distilled_file):
    with open(distilled_file, "r", encoding="utf-8") as f:
        dist_code = f.read()
    dist_code = dist_code.replace("self.dtype = torch.bfloat16", "self.dtype = getattr(models, 'dtype', torch.float16)")
    dist_code = dist_code.replace("dtype = torch.bfloat16", "dtype = getattr(self, 'dtype', torch.float16)")
    with open(distilled_file, "w", encoding="utf-8") as f:
        f.write(dist_code)

# Patch CausalConv3d in Wan2GP video_vae to prevent dtype mismatch between latents and VAE conv weights
conv_file = os.path.join(WAN2GP_DIR, "models", "ltx2", "ltx_core", "model", "video_vae", "convolution.py")
if os.path.isfile(conv_file):
    with open(conv_file, "r", encoding="utf-8") as f:
        conv_code = f.read()
    if "x = self.conv(x)" in conv_code and "x.dtype != self.conv.weight.dtype" not in conv_code:
        conv_code = conv_code.replace(
            "        x = self.conv(x)",
            "        if hasattr(self, 'conv') and hasattr(self.conv, 'weight') and x.dtype != self.conv.weight.dtype:\n            x = x.to(dtype=self.conv.weight.dtype)\n        x = self.conv(x)"
        )
        with open(conv_file, "w", encoding="utf-8") as f:
            f.write(conv_code)

# Patch audio_vae.py in Wan2GP to auto-cast latents to audio decoder and vocoder weight dtypes
audio_vae_file = os.path.join(WAN2GP_DIR, "models", "ltx2", "ltx_core", "model", "audio_vae", "audio_vae.py")
if os.path.isfile(audio_vae_file):
    with open(audio_vae_file, "r", encoding="utf-8") as f:
        audio_vae_code = f.read()
    if "decoded_audio = audio_decoder(latent)" in audio_vae_code and "latent.to(dtype=" not in audio_vae_code:
        audio_vae_code = audio_vae_code.replace(
            "    decoded_audio = audio_decoder(latent)",
            "    if hasattr(audio_decoder, 'conv_in') and hasattr(audio_decoder.conv_in, 'weight'):\n        latent = latent.to(dtype=audio_decoder.conv_in.weight.dtype)\n    decoded_audio = audio_decoder(latent)\n    if hasattr(vocoder, 'vocoder') and hasattr(vocoder.vocoder, 'conv_pre'):\n        decoded_audio = decoded_audio.to(dtype=vocoder.vocoder.conv_pre.weight.dtype)"
        )
        with open(audio_vae_file, "w", encoding="utf-8") as f:
            f.write(audio_vae_code)

# Patch vocoder.py in Wan2GP to prevent buffer dtype mismatch in LowPassFilter1d and STFT
vocoder_file = os.path.join(WAN2GP_DIR, "models", "ltx2", "ltx_core", "model", "audio_vae", "vocoder.py")
if os.path.isfile(vocoder_file):
    with open(vocoder_file, "r", encoding="utf-8") as f:
        vocoder_code = f.read()
    vocoder_code = vocoder_code.replace(
        "return F.conv1d(x, self.filter.expand(n_channels, -1, -1), stride=self.stride, groups=n_channels)",
        "filt = self.filter.to(dtype=x.dtype, device=x.device).expand(n_channels, -1, -1)\n        return F.conv1d(x, filt, stride=self.stride, groups=n_channels)"
    )
    vocoder_code = vocoder_code.replace(
        "spec = F.conv1d(y, self.forward_basis, stride=self.hop_length, padding=0)",
        "basis = self.forward_basis.to(dtype=y.dtype, device=y.device)\n        spec = F.conv1d(y, basis, stride=self.hop_length, padding=0)"
    )
    with open(vocoder_file, "w", encoding="utf-8") as f:
        f.write(vocoder_code)

# Patch PixelNorm in Wan2GP to compute RMS in float32 (fixes FP16 overflow into flat gray background)
norm_file = os.path.join(WAN2GP_DIR, "models", "ltx2", "ltx_core", "model", "common", "normalization.py")
if os.path.isfile(norm_file):
    with open(norm_file, "r", encoding="utf-8") as f:
        norm_code = f.read()
    if "x_float = x.float()" not in norm_code:
        norm_code = norm_code.replace(
            "        mean_sq = torch.mean(x**2, dim=self.dim, keepdim=True)\n        # Normalize by the root-mean-square (RMS).\n        rms = torch.sqrt(mean_sq + self.eps)\n        return x / rms",
            "        orig_dtype = x.dtype\n        x_float = x.float()\n        mean_sq = torch.mean(x_float**2, dim=self.dim, keepdim=True)\n        rms = torch.sqrt(mean_sq + self.eps)\n        return (x_float / rms).to(orig_dtype)"
        )
        with open(norm_file, "w", encoding="utf-8") as f:
            f.write(norm_code)

# Patch feature_extractor.py in Wan2GP to compute token RMS in float32
fe_file = os.path.join(WAN2GP_DIR, "models", "ltx2", "ltx_core", "text_encoders", "gemma", "feature_extractor.py")
if os.path.isfile(fe_file):
    with open(fe_file, "r", encoding="utf-8") as f:
        fe_code = f.read()
    if "enc_f = encoded_text.float()" not in fe_code:
        fe_code = fe_code.replace(
            "def _norm_and_concat_per_token_rms(encoded_text: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:\n    b, t, d, l = encoded_text.shape\n    variance = torch.mean(encoded_text**2, dim=2, keepdim=True)\n    normed = encoded_text * torch.rsqrt(variance + 1e-6)\n    normed = normed.reshape(b, t, d * l)\n    mask_3d = attention_mask.bool().unsqueeze(-1)\n    return torch.where(mask_3d, normed, torch.zeros_like(normed))",
            "def _norm_and_concat_per_token_rms(encoded_text: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:\n    orig_dtype = encoded_text.dtype\n    enc_f = encoded_text.float()\n    b, t, d, l = enc_f.shape\n    variance = torch.mean(enc_f**2, dim=2, keepdim=True)\n    normed = enc_f * torch.rsqrt(variance + 1e-6)\n    normed = normed.reshape(b, t, d * l).to(orig_dtype)\n    mask_3d = attention_mask.bool().unsqueeze(-1)\n    return torch.where(mask_3d, normed, torch.zeros_like(normed))"
        )
        with open(fe_file, "w", encoding="utf-8") as f:
            f.write(fe_code)

import gradio as gr
from shared.utils.audio_video import save_video
from mmgp import offload, quant_router
from models.ltx2.ltx2_handler import family_handler

# Register Wan2GP custom quantization handlers (INT8 ConvRot, FP8, NVFP4, GGUF) with mmgp
_HANDLER_MODULES = [
    "shared.qtypes.scaled_fp8",
    "shared.qtypes.nvfp4",
    "shared.qtypes.bnb_nf4",
    "shared.qtypes.nunchaku_int4",
    "shared.qtypes.nunchaku_fp4",
    "shared.qtypes.asym_w4a8_int8",
    "shared.qtypes.int8_convrot",
    "shared.qtypes.gguf",
]
quant_router.unregister_handler(".fp8_quanto_bridge")
for handler in _HANDLER_MODULES:
    quant_router.register_handler(handler)
from shared.qtypes import gguf as gguf_handler
quant_router.register_file_extension("gguf", gguf_handler)

# ==== GPU INFO ====
gpu_count = torch.cuda.device_count()
print(f"GPUs Available: {gpu_count}")
for i in range(gpu_count):
    print(f"  GPU {i}: {torch.cuda.get_device_name(i)} ({torch.cuda.get_device_properties(i).total_memory / 1024**3:.1f} GB VRAM)")

ram = psutil.virtual_memory()
print(f"RAM: {ram.total / 1024**3:.1f} GB total, {ram.available / 1024**3:.1f} GB available")
sys.stdout.flush()

# ==== LOAD LTX-2.5 22B DISTILLED MODEL IN-MEMORY (HIGH-SPEED BUDGET ARCHITECTURE) ====
print("\n=== Loading LTX-2.5 22B Distilled Model in Memory (One-Time Startup) ===")
sys.stdout.flush()

base_model_type = "ltx2_25_22B"
model_def = {
    "ltx2_pipeline": "distilled",
    "name": "LTX-2 2.5 Distilled 22B",
    "architecture": "ltx2_25_22B"
}
extra = family_handler.query_model_def(base_model_type, model_def)
model_def.update(extra)

# Auto-resolve and verify text encoder and transformer paths
for base_path in ["models", "ckpts"]:
    nested_gemma = os.path.join(base_path, "gemma4-12b-ltx-v1", "gemma4-12b-ltx-v1")
    if os.path.isdir(nested_gemma):
        for f in os.listdir(nested_gemma):
            dst = os.path.join(base_path, "gemma4-12b-ltx-v1", f)
            if not os.path.exists(dst):
                try:
                    os.replace(os.path.join(nested_gemma, f), dst)
                except Exception:
                    pass

# Ensure all symlinks exist between /tmp/models, models/, and ckpts/
for d_from in ["/tmp/models", "models"]:
    if os.path.exists(d_from):
        for f in os.listdir(d_from):
            if f.startswith("."): continue
            src = os.path.join(d_from, f)
            for d_to in ["models", "ckpts"]:
                dst = os.path.join(d_to, f)
                if not os.path.exists(dst):
                    try:
                        os.symlink(os.path.abspath(src), dst)
                    except Exception:
                        pass

# Specifically link gemma4-12b-ltx-v1 folder contents
for gf in ["gemma4-12b-ltx-v1_int8_convrot.safetensors", "config.json", "chat_template.jinja", "tokenizer.json", "tokenizer_config.json"]:
    src_gm = os.path.join("models", "gemma4-12b-ltx-v1", gf)
    dst_gc = os.path.join("ckpts", "gemma4-12b-ltx-v1", gf)
    os.makedirs(os.path.dirname(dst_gc), exist_ok=True)
    if os.path.exists(src_gm) and not os.path.exists(dst_gc):
        try:
            os.symlink(os.path.abspath(src_gm), dst_gc)
        except Exception:
            pass

text_encoder_file = "ckpts/gemma4-12b-ltx-v1/gemma4-12b-ltx-v1_int8_convrot.safetensors"
if not os.path.exists(text_encoder_file):
    text_encoder_file = "models/gemma4-12b-ltx-v1/gemma4-12b-ltx-v1_int8_convrot.safetensors"

transformer_path = "models/ltx-2.5-22b-distilled_diffusion_model_int8_convrot.safetensors"
if not os.path.exists(transformer_path):
    transformer_path = "ckpts/ltx-2.5-22b-distilled_diffusion_model_int8_convrot.safetensors"
if not os.path.exists(transformer_path) and os.path.exists("/tmp/models/ltx-2.5-22b-distilled_diffusion_model_int8_convrot.safetensors"):
    transformer_path = "/tmp/models/ltx-2.5-22b-distilled_diffusion_model_int8_convrot.safetensors"

print(f"  Transformer : {os.path.basename(transformer_path)}")
print(f"  Text Encoder: {os.path.basename(text_encoder_file)}")
sys.stdout.flush()

MODEL_DTYPE = torch.float16
VAE_DTYPE   = torch.float16

with torch.inference_mode():
    with torch.set_grad_enabled(False):
        wan_model, pipe = family_handler.load_model(
            model_filename=transformer_path,
            model_type="ltx2_25_22B_distilled",
            base_model_type=base_model_type,
            model_def=model_def,
            dtype=MODEL_DTYPE,
            VAE_dtype=VAE_DTYPE,
            text_encoder_filename=text_encoder_file,
        )

kwargs = {}
if isinstance(pipe, dict) and "pipe" in pipe:
    kwargs = pipe
    pipe = kwargs.pop("pipe")

loras = kwargs.pop("loras", [])

if "transformer" in pipe and "transformer" not in loras:
    loras.append("transformer")

print("\nApplying mmgp Profile 4 with Partial Pinning & Free RAM Headroom (6000 MB transformer budget, Async DMA Transfers)...")
sys.stdout.flush()

offload.profile(
    pipe,
    profile_no=4,
    pinnedMemory="transformer",
    partialPinning=True,
    perc_reserved_mem_max=0.35,
    asyncTransfers=True,
    quantizeTransformer=False,
    convertWeightsFloatTo=torch.float16,
    loras=loras,
    budgets={
        # 6000 MB transformer budget keeps ~8.5 GB VRAM free for zero-thrashing SDPA attention
        "transformer":       6000,
        "text_encoder":      1500,
        "video_encoder":     2000,
        "video_decoder":     3000,
        "audio_encoder":     1000,
        "audio_decoder":     1000,
        "vocoder":           500,
        "spatial_upsampler": 1500,
        "vae":               1000,
        "*":                 1000,
    },
    **kwargs
)

offload.shared_state["_attention"] = "sdpa"
offload.shared_state["_radial"] = False

print("\n✅ Setup complete! LTX-2.5 22B Distilled Model loaded & pinned in memory permanently.")
sys.stdout.flush()

# ==== RESOLUTION PRESETS ====
def get_resolution(preset_str, aspect_ratio_str):
    base_resolutions = {
        "Fast Preview (384p - ~1-2 min)": 384,
        "Balanced (480p - ~3-5 min)": 480,
        "High Quality (704p - ~6-8 min)": 704,
        "Cinema 1080p (1088p - High Detail)": 1088,
    }
    ratios = {
        "16:9 Landscape": 16/9, "4:3 Standard": 4/3,
        "1:1 Square": 1.0, "3:4 Portrait": 3/4, "9:16 Portrait": 9/16,
    }
    base = base_resolutions.get(preset_str, 384)
    ratio = ratios.get(aspect_ratio_str, 16/9)
    if ratio >= 1.0:
        height = base
        width = int(base * ratio)
    else:
        width = base
        height = int(base / ratio)
    return (width // 32) * 32, (height // 32) * 32

# ==== REAL-TIME STREAMING VIDEO GENERATION (TIMEOUT-FREE) ====
def Video_Generation(prompt, input_image_start, input_image_end, seed, duration_dropdown,
                     resolution_dropdown, aspect_ratio_dropdown,
                     guide_scale=3.0, audio_cfg=7.0, num_steps=8):
    try:
        gc.collect(); torch.cuda.empty_cache(); torch.cuda.synchronize()
        offload.shared_state["_attention"] = "sdpa"
        offload.shared_state["_radial"] = False

        duration_map = {
            "2 Seconds (49 frames - Fast)": 49,
            "3 Seconds (73 frames - Standard)": 73,
            "5 Seconds (121 frames - Long)": 121,
            "8 Seconds (193 frames)": 193,
            "10 Seconds (241 frames)": 241,
        }
        frame_rate = 24.0
        num_frames = duration_map.get(duration_dropdown, 73)
        width, height = get_resolution(resolution_dropdown, aspect_ratio_dropdown)

        if seed is None or seed < 0:
            seed = random.randint(0, 2**32 - 1)
        seed = int(seed)

        image_start = None
        image_end   = None
        if input_image_start is not None:
            image_start = Image.open(input_image_start).convert("RGB")
        if input_image_end is not None:
            image_end = Image.open(input_image_end).convert("RGB")

        free_vram = torch.cuda.mem_get_info()[0] / 1024**3
        ram = psutil.virtual_memory()
        mode = "T2V" if image_start is None else ("I2V first+last" if image_end else "I2V start")

        print(f"\n{'='*60}")
        print(f"🎬 Generating LTX-2.5 [{mode}]: {width}x{height}, {num_frames} frames (~{num_frames/24.0:.1f}s), seed={seed}")
        print(f"  VRAM free: {free_vram:.2f} GB | RAM free: {ram.available / 1024**3:.1f} GB")
        print(f"  Prompt: {prompt[:120]}{'...' if len(prompt) > 120 else ''}")
        print(f"  Video CFG: {guide_scale} | Audio CFG: {audio_cfg} | Steps: {num_steps}")
        print(f"{'='*60}")
        sys.stdout.flush()

        yield None, f"⏳ Initializing LTX-2.5 [{mode}] ({width}x{height}, {num_frames} frames, seed: {seed})..."

        # Progress queue for real-time WebSocket updates across threads
        msg_queue = queue.Queue()
        total_steps = [int(num_steps)]
        current_step = [0]
        step_times = []
        last_step_time = [time.time()]

        def cb(step, latent, is_start, override_num_inference_steps=None, pass_no=None, **kwargs):
            if is_start:
                if override_num_inference_steps is not None:
                    total_steps[0] = override_num_inference_steps
                current_step[0] = 0
                last_step_time[0] = time.time()
                return
            now = time.time()
            dt = now - last_step_time[0]
            last_step_time[0] = now
            step_times.append(dt)
            current_step[0] += 1
            free_v = torch.cuda.mem_get_info()[0] / 1024**3
            avg_dt = sum(step_times) / len(step_times)
            rem_steps = max(total_steps[0] - current_step[0], 0)
            rem_sec = rem_steps * avg_dt
            msg = f"⚡ Denoising step {current_step[0]}/{total_steps[0]} ({dt:.1f}s/step | ~{rem_sec:.0f}s left | VRAM: {free_v:.1f} GB free)"
            print(f"  [Denoising] {msg}")
            sys.stdout.flush()
            msg_queue.put(msg)

        _stage_labels = {
            "VAE Encoding": "🎞️ VAE Encoding input frames...",
            "VAE Decoding": "🎬 VAE Decoding latents → video frames...",
            "Upsampling":   "🔭 Spatial upsampling latents...",
        }

        def set_progress_status(status: str):
            label = _stage_labels.get(status, f"⏳ {status}...")
            print(f"  [{status}] {label}")
            sys.stdout.flush()
            msg_queue.put(label)
            if "Decoding" in status or "Upsampling" in status:
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        gen_kwargs = dict(
            input_prompt=prompt,
            image_start=image_start,
            height=height,
            width=width,
            frame_num=num_frames,
            fps=frame_rate,
            seed=seed,
            callback=cb,
            VAE_tile_size=0,
            input_video_strength=1.0,
            denoising_strength=1.0,
            guide_scale=float(guide_scale),
            audio_cfg_scale=float(audio_cfg),
            sampling_steps=int(num_steps),
            guide_phases=1,
            sample_solver="distilled_8_steps",
            self_refiner_setting=0,
            n_prompt="",
            set_progress_status=set_progress_status,
        )
        if image_end is not None:
            gen_kwargs["image_end"] = image_end

        result_holder = {}
        error_holder = {}

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        def run_generation():
            try:
                t0 = time.time()
                res = wan_model.generate(**gen_kwargs)
                result_holder["result"] = res
                result_holder["elapsed"] = time.time() - t0
            except Exception as exc:
                error_holder["error"] = exc
                traceback.print_exc()

        gen_thread = threading.Thread(target=run_generation)
        gen_thread.start()

        # Stream periodic WebSocket heartbeats while generation is in progress
        last_yield_time = time.time()
        current_status = "⏳ Starting in-memory single-stage 8-step generation..."
        while gen_thread.is_alive():
            # Check for new step messages
            updated = False
            while not msg_queue.empty():
                current_status = msg_queue.get_nowait()
                updated = True

            # Yield heartbeat every 2 seconds to keep WebSocket proxy alive
            now = time.time()
            if updated or (now - last_yield_time >= 2.0):
                last_yield_time = now
                yield None, current_status
            time.sleep(0.5)

        gen_thread.join()

        if "error" in error_holder:
            raise error_holder["error"]

        result = result_holder.get("result")
        elapsed = result_holder.get("elapsed", 0)
        print(f"  [Pipeline Completed] Finished in {elapsed:.1f}s")
        sys.stdout.flush()

        yield None, f"🎬 Generation finished in {elapsed:.1f}s! Saving MP4 and muxing audio..."

        if result is None:
            yield None, "❌ Generation returned no output."
            return

        audio_data = None
        audio_sr = 24000
        if isinstance(result, dict):
            video_tensor = result.get("x")
            audio_data   = result.get("audio")
            audio_sr     = result.get("audio_sampling_rate", 24000)
        elif isinstance(result, tuple):
            video_tensor = result[0]
            audio_data   = result[1] if len(result) > 1 else None
            audio_sr     = result[2] if len(result) > 2 else 24000
        else:
            video_tensor = result
            audio_data, audio_sr = None, 24000

        if video_tensor is None or not torch.is_tensor(video_tensor):
            yield None, f"❌ No video tensor returned. Got: {type(video_tensor)}"
            return

        video_tensor = video_tensor.cpu()
        gc.collect(); torch.cuda.empty_cache()

        # Save video directly to physical disk OUTPUTS_DIR (not tmpfs RAM)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_filename = f"ltx25_{timestamp}_seed{seed}.mp4"
        out_path = os.path.join(OUTPUTS_DIR, out_filename)

        if video_tensor.dtype != torch.uint8:
            video_tensor = video_tensor.clamp(0, 255).to(torch.uint8)
        if video_tensor.ndim == 4:
            video_tensor = video_tensor.unsqueeze(0)
        save_video(tensor=video_tensor, save_file=out_path, fps=frame_rate, nrow=1)

        # Also copy to /kaggle/working/outputs for external access
        try:
            import shutil
            shutil.copy2(out_path, os.path.join("/kaggle/working/outputs", out_filename))
        except Exception:
            pass

        # ==== Mux native synchronized audio (if generated) ====
        if audio_data is not None:
            try:
                audio_tmp = tempfile.mktemp(suffix=".wav")
                if isinstance(audio_data, np.ndarray):
                    audio_np = audio_data
                    if audio_np.ndim == 2 and audio_np.shape[0] <= 2 and audio_np.shape[1] > audio_np.shape[0]:
                        audio_np = audio_np.T
                    sf.write(audio_tmp, audio_np, int(audio_sr or 24000))
                elif torch.is_tensor(audio_data):
                    import torchaudio
                    cpu_audio = audio_data.cpu().float()
                    if cpu_audio.dim() == 1: cpu_audio = cpu_audio.unsqueeze(0)
                    if cpu_audio.dim() == 3: cpu_audio = cpu_audio.squeeze(0)
                    torchaudio.save(audio_tmp, cpu_audio, int(audio_sr or 24000))

                final_path = out_path.replace(".mp4", "_with_audio.mp4")
                subprocess.run([
                    "ffmpeg", "-y", "-i", out_path, "-i", audio_tmp,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", final_path
                ], check=True, capture_output=True)
                if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
                    out_path = final_path
                    # Copy audio-muxed version to persistent storage
                    try:
                        shutil.copy2(out_path, os.path.join("/kaggle/working/outputs", os.path.basename(final_path)))
                        shutil.copy2(out_path, os.path.join(OUTPUTS_DIR, os.path.basename(final_path)))
                    except Exception:
                        pass
                    print(f"  ✅ Synchronized audio muxed into output: {out_path}")
            except Exception as e:
                print(f"  ⚠️ Audio mux note: {e}")

        del video_tensor
        gc.collect(); torch.cuda.empty_cache()

        yield out_path, f"✅ Video generated in {elapsed:.1f}s! Seed: {seed} | {width}x{height} | {num_frames} frames | Saved: {out_path}"

    except Exception as e:
        traceback.print_exc()
        gc.collect(); torch.cuda.empty_cache()
        yield None, f"❌ Error: {str(e)}"

# ==== GRADIO UI (AIQUEST BRANDED) ====
CSS = '''@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
* { font-family: 'Inter', sans-serif !important; }
.gradio-container { max-width: 1050px !important; margin: auto !important; }
.brand-header { text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 28px; border-radius: 15px; margin-bottom: 20px; box-shadow: 0 10px 25px rgba(102,126,234,0.3); }
.brand-title { color: white; font-size: 2em; font-weight: 700; margin: 0 0 6px 0; }
.brand-subtitle { color: rgba(255,255,255,0.88); font-size: 1em; margin-bottom: 16px; }
.social-buttons { display: flex; justify-content: center; gap: 12px; flex-wrap: wrap; }
.social-btn { padding: 10px 24px; border-radius: 8px; font-weight: 700; font-size: 15px; text-decoration: none; display: inline-block; color: white !important; transition: all 0.3s; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
.social-btn:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0,0,0,0.3); }
.youtube-btn { background: linear-gradient(135deg, #FF0000 0%, #CC0000 100%); }
.x-btn { background: linear-gradient(135deg, #000000 0%, #333333 100%); }
button.primary, #gen-btn { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; color: white !important; font-weight: 600 !important; border-radius: 12px !important; }
#stop-btn { background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%) !important; color: white !important; font-weight: 600 !important; border-radius: 12px !important; }
#clear-btn { background: linear-gradient(135deg, #6b7280 0%, #374151 100%) !important; color: white !important; font-weight: 600 !important; border-radius: 12px !important; }
.footer { text-align: center; padding: 20px; margin-top: 30px; border-top: 2px solid #e5e7eb; color: #6b7280; }
'''

with gr.Blocks(css=CSS, theme=gr.themes.Soft(), title="LTX-2.5 22B Distilled - AIQUEST Academy") as demo:
    gr.HTML('<div class="brand-header"><div class="brand-title">🎬 LTX-2.5 22B Distilled - Video Generator</div><div class="brand-subtitle">Created by <strong>AIQUEST Academy</strong> | Kaggle Dual T4 GPU Edition</div><div class="social-buttons"><a href="https://www.youtube.com/@aiquestacademy?sub_confirmation=1" target="_blank" class="social-btn youtube-btn">▶️ Subscribe on YouTube</a><a href="https://x.com/aiquestacademy" target="_blank" class="social-btn x-btn">𝕏 Follow on X</a></div></div>')

    gr.Markdown(
        '''**Single-Stage 8-Step Distilled Pipeline** | Official INT8 Convrot (~19.5 GB) | Persistent In-Memory Model

⚡ **Performance Presets:** Use **Fast Preview (384p, 2s/3s)** for rapid ~1-2 minute generation. All generated videos are automatically saved to `/kaggle/working/outputs/`.'''
    )

    with gr.Row():
        with gr.Column(scale=1):
            prompt = gr.Textbox(
                label="🎨 Prompt", lines=3,
                placeholder="A cinematic 4k close-up shot of a majestic snow leopard in the Himalayas during a snowfall, breathing softly, ultra realistic..."
            )

            with gr.Accordion("🖼️ Image to Video (Optional)", open=False):
                with gr.Row():
                    input_image_start = gr.Image(type="filepath", label="🎬 Start Frame (First Frame)", height=180)
                    input_image_end   = gr.Image(type="filepath", label="🎬 End Frame (Last Frame - Optional)", height=180)
                gr.Markdown(
                    '''*• **Start Frame only** → Image-to-Video (model generates from your image)*
*• **Both frames** → First+Last frame interpolation (model generates in-between)*
*• **Neither** → Pure Text-to-Video*'''
                )

            with gr.Row():
                duration_dropdown = gr.Dropdown(
                    label="⏱️ Duration",
                    choices=[
                        "2 Seconds (49 frames - Fast)",
                        "3 Seconds (73 frames - Standard)",
                        "5 Seconds (121 frames - Long)",
                        "8 Seconds (193 frames)",
                        "10 Seconds (241 frames)",
                    ],
                    value="5 Seconds (121 frames - Long)",
                )
                resolution_dropdown = gr.Dropdown(
                    label="📐 Resolution Preset",
                    choices=[
                        "Fast Preview (384p - ~1-2 min)",
                        "Balanced (480p - ~3-5 min)",
                        "High Quality (704p - ~6-8 min)",
                        "Cinema 1080p (1088p - High Detail)",
                    ],
                    value="Balanced (480p - ~3-5 min)",
                )
                aspect_ratio_dropdown = gr.Dropdown(
                    label="📏 Aspect Ratio",
                    choices=["16:9 Landscape", "4:3 Standard", "1:1 Square", "3:4 Portrait", "9:16 Portrait"],
                    value="16:9 Landscape",
                )

            with gr.Row():
                guide_scale = gr.Slider(
                    label="🎯 Video CFG Scale (Distilled: 1.0 recommended)",
                    minimum=1.0, maximum=3.0, step=0.1, value=1.0,
                )
                audio_cfg = gr.Slider(
                    label="🔊 Audio CFG Scale",
                    minimum=1.0, maximum=5.0, step=0.5, value=1.0,
                )

            with gr.Row():
                num_steps = gr.Slider(
                    label="⚡ Denoising Steps",
                    minimum=4, maximum=12, step=1, value=8,
                )
                seed = gr.Number(label="🎲 Seed (-1 for Random)", value=-1, precision=0)

            with gr.Row():
                gen_btn   = gr.Button("🎬 Generate Video", variant="primary", size="lg", elem_id="gen-btn")
                stop_btn  = gr.Button("🛑 Stop",            variant="secondary", size="lg", elem_id="stop-btn")
                clear_btn = gr.Button("🗑️ Clear",           variant="secondary", size="lg", elem_id="clear-btn")

        with gr.Column(scale=1):
            video_out  = gr.Video(label="🎥 Generated Video with Synchronized Audio", height=420)
            status_out = gr.Textbox(label="ℹ️ Live Progress & Output Path", interactive=False, lines=2)

    gr.HTML('<div class="footer"><p style="font-size: 16px; margin: 5px 0; text-align: center;">🎬 Created by <strong>AIQUEST Academy</strong></p><p style="font-size: 14px; margin: 5px 0; color: #9ca3af; text-align: center;">Official LTX-2.5 22B Distilled INT8 Convrot | Kaggle Dual GPU (GPU T4 x2)</p><p style="font-size: 13px; margin: 10px 0; text-align: center;"><a href="https://www.youtube.com/@aiquestacademy?sub_confirmation=1" target="_blank" style="color: #667eea; text-decoration: none; margin: 0 10px;">YouTube</a> • <a href="https://x.com/aiquestacademy" target="_blank" style="color: #667eea; text-decoration: none; margin: 0 10px;">X (Twitter)</a></p></div>')

    gen_event = gen_btn.click(
        fn=Video_Generation,
        inputs=[prompt, input_image_start, input_image_end, seed, duration_dropdown,
                resolution_dropdown, aspect_ratio_dropdown, guide_scale, audio_cfg, num_steps],
        outputs=[video_out, status_out],
    )
    stop_btn.click(fn=None, cancels=[gen_event])
    clear_btn.click(
        fn=lambda: (None, None, None, "", -1),
        outputs=[input_image_start, input_image_end, video_out, prompt, seed],
    )

print("\n🚀 Launching AIQUEST Academy Gradio Web Interface...")
sys.stdout.flush()
demo.queue(max_size=20, default_concurrency_limit=1)

allowed_paths = [
    os.path.abspath("outputs"),
    os.path.abspath(WAN2GP_DIR),
    "/kaggle/working",
    "/kaggle/working/outputs",
    "/kaggle/working/Wan2GP",
    "/tmp",
    tempfile.gettempdir()
]

demo.launch(
    share=True,
    inline=False,
    debug=True,
    show_error=True,
    max_threads=4,
    ssr_mode=False,
    allowed_paths=allowed_paths
)
