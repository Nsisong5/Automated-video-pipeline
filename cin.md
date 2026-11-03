why do we have contradiction and the change in some values 
here is what I sent over the API

{
  "title": "Chaining Test",
  "channel_id": "testch",
  "scenes": [
    {
      "prompt": "A peaceful mountain lake at sunset",
      "duration_seconds": 2,
      "chain_from_previous": false
    },
    {
      "prompt": "A ripple starts on the lake surface",
      "duration_seconds": 2,
      "chain_from_previous": true
    },
    {
      "prompt": "A close up of the water ripple",
      "duration_seconds": 2,
      "chain_from_previous": true
    }
  ]
}


here is what I got inside of kaggle as a job


{
  "jobs": [
    {
      "prompt": "A peaceful mountain lake at sunset",
      "duration": "2 Seconds (49 frames - Fast)",
      "resolution": "Fast Preview (384p - ~1-2 min)",
      "seed": -1,
      "chain_from_previous": false
    },
    {
      "prompt": "A ripple starts on the lake surface",
      "duration": "2 Seconds (49 frames - Fast)",
      "resolution": "Fast Preview (384p - ~1-2 min)",
      "seed": -1,
      "chain_from_previous": false
    },
    {
      "prompt": "A close up of the water ripple",
      "duration": "2 Seconds (49 frames - Fast)",
      "resolution": "Fast Preview (384p - ~1-2 min)",
      "seed": -1,
      "chain_from_previous": false
    }
  ]
}




why are the values of "chain_from_previous" modified wrongly
