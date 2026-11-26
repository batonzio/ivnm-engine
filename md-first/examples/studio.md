# IVNM MD-first example — synthetic public test

The first scene demonstrates expressive requirements. It must be blocked until a suitable native instruction-conditioned model is configured. The second is a neutral CPU smoke test.

```ivnm-voice
id: mystery-dialogue
lesson: demo-09
slide: listening-01
profile: school_dialogue
quality: studio
accent: British RP
direction: "Two friends are discussing a strange event. Keep the acting subtle and realistic."
speakers:
  Oliver: marius
  Emily: alba
script:
  - speaker: Oliver
    text: "So, what exactly did you see?"
    emotion: curiosity
    direction: "Genuine interest; emphasise exactly."
    emphasis: [exactly]
    pause_after_ms: 260
  - speaker: Emily
    text: "Well... there was a strange light."
    emotion: uncertainty
    direction: "Hesitant at first, then more certain."
    pause_after_ms: 480
```

```ivnm-voice
id: neutral-cpu-smoke
lesson: demo-05
slide: listening-01
profile: neutral_benchmark
quality: draft
takes: 1
speakers:
  A: alba
  B: marius
script:
  - speaker: A
    text: "Is there a desk next to your bed?"
    pause_after_ms: 320
  - speaker: B
    text: "Yes, there is. I use it to do my homework."
```
