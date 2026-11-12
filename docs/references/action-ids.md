# Action IDs

Action IDs identify active local tool operations. Each is a stable `A` plus
five uppercase alphanumeric characters, declared by its handler. Every
registered operation has one row. No registered handler returns
`NOT_IMPLEMENTED`; optional backends report typed provider/configuration errors.

| ID | Operation | Meaning |
| --- | --- | --- |
| `A2A7K4` | `audio(operation=probe)` | Inspect audio metadata |
| `A4R8D2` | `audio(operation=trim)` | Trim an audio file with bounded ffmpeg arguments |
| `A1C6V9` | `audio(operation=convert)` | Convert an audio file to a supported format |
| `A4M9Q2` | `calculate(operation=evaluate)` | Evaluate a calculation |
| `A9C5J8` | `clock(operation=now)` | Retrieve the current time |
| `A7T4M1` | `clock(operation=convert)` | Convert an ISO 8601 timestamp between timezones |
| `A6P3N8` | `data(operation=table)` | Analyze a dataset |
| `A8Q1R5` | `data(operation=sql)` | Run an allowed read-only SQL query |
| `A3D9W2` | `data(operation=profile)` | Profile a dataset |
| `A5J4H7` | `data(operation=join)` | Join two tabular datasets |
| `A1V6C3` | `data(operation=report)` | Compile report sections |
| `A7B2L9` | `data(operation=chart)` | Create a chart |
| `A6E4X8` | `extract(operation=json)` | Validate and isolate embedded JSON |
| `A2Q9B4` | `extract(operation=xml)` | Parse bounded XML text |
| `A5Z1K7` | `extract(operation=yaml)` | Parse safe bounded YAML text |
| `A9L3F6` | `extract(operation=csv)` | Parse bounded CSV text |
| `A3F8Q1` | `fetch(operation=url)` | Retrieve text from an allowlisted HTTPS page |
| `A6F2J9` | `fetch(operation=pdf)` | Retrieve and extract text from an allowlisted HTTPS PDF |
| `A9D4K7` | `fetch(operation=json)` | Retrieve and parse JSON from an allowlisted HTTPS URL |
| `A2G7M4` | `generate(operation=image)` | Generate a local image with Forge Canvas |
| `A5A1D8` | `generate(operation=audio)` | Generate speech audio with Forge Voice |
| `A9F3A6` | `image(operation=info)` | Read image dimensions and format |
| `A2H8K1` | `image(operation=resize)` | Resize an image |
| `A3W7C2` | `image(operation=ocr)` | Extract text from an image |
| `A5R2N6` | `image(operation=generate)` | Generate and save an image with Forge Canvas |
| `A4P8C2` | `pdf(operation=text)` | Extract bounded text from a local PDF |
| `A78ORH` | `search(operation=web)` | Search the public web |
| `A2I4M6` | `search(operation=image)` | Search public image results |
| `A7N3W5` | `search(operation=news)` | Search public news results |
| `A1G9V4` | `sheet(operation=read)` | Read CSV headers and rows |
| `A7K3Q8` | `sheet(operation=write)` | Write rows to a CSV file |
| `A6I2N5` | `sheet(operation=info)` | Inspect CSV headers and row count |
| `A8S4P2` | `speak(operation=text)` | Generate spoken audio from text |
| `A4S9U2` | `summarize(operation=text)` | Select salient source sentences |
| `A8C5D3` | `summarize(operation=url)` | Summarize an allowlisted HTTPS text page |
| `A5T8R1` | `transcribe(operation=audio)` | Transcribe audio to text |
| `A2T6V8` | `translate(operation=text)` | Translate text with Forge Text |
| `A7D1K4` | `translate(operation=document)` | Translate a sandboxed UTF-8 document |
| `A4X6B2` | `video(operation=probe)` | Inspect video metadata |
| `A9A1M7` | `video(operation=sample)` | Extract frames at requested timestamps |
| `A2C8R5` | `video(operation=keyframe)` | Extract scene-change keyframes |
| `A3W2F9` | `weather(operation=current)` | Retrieve current weather from Open-Meteo |
| `A7F6L1` | `weather(operation=forecast)` | Retrieve a short Open-Meteo forecast |

Unrestricted code/shell execution, interactive browser control, image
analysis/detection, video generation, and PDF table/image extraction are not
registered. Their historic IDs are not reused.
