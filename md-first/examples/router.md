# Three-engine smoke tests (not approved production voices)

```ivnm-voice
id: pocket-smoke
profile: neutral_benchmark
takes: 1
speakers: {A: alba, B: charles}
script:
  - speaker: A
    text: "Did you enjoy the exhibition?"
    pause_after_ms: 320
  - speaker: B
    text: "Yes, it was wonderful."
```

```ivnm-voice
id: chatterbox-smoke
profile: neutral_benchmark
takes: 1
speakers: {A: chatterbox_default, B: chatterbox_charles}
script:
  - speaker: A
    text: "Did you enjoy the exhibition?"
    pause_after_ms: 320
  - speaker: B
    text: "Yes, it was wonderful."
```

```ivnm-voice
id: kitten-smoke
profile: neutral_benchmark
takes: 1
speakers: {A: kitten_bella, B: kitten_jasper}
script:
  - speaker: A
    text: "Did you enjoy the exhibition?"
    pause_after_ms: 320
  - speaker: B
    text: "Yes, it was wonderful."
    emotion: joyful
    emphasis: [wonderful]
```
