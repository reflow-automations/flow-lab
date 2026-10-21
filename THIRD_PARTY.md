# Onderdelen van derden

De MIT-licentie in dit project geldt voor de eigen Flow Lab-broncode. Pakketten,
modellen en native runtimes behouden hun eigen licentie. Dit broncodepakket
bevat geen modelgewichten, native binaries of Python site-packages. Installatie
haalt die afzonderlijk bij de genoemde bronnen op.

## Modelservers en gewichten

| Onderdeel | Gebruik | Licentie / bron |
| --- | --- | --- |
| NVIDIA NeMo-Speech.cpp v0.2.0 | Parakeet uitvoeren | [Apache-2.0](https://github.com/NVIDIA/NeMo-Speech.cpp/blob/v0.2.0/LICENSE) |
| NVIDIA parakeet-tdt-0.6b-v3 | Spraak naar tekst | [CC-BY-4.0, model card en governing terms](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3/blob/541d1f99c6b0c3cd0b11a95167540bb8edefd82b/README.md) |
| llama.cpp b11658 | Lokaal opmaakmodel uitvoeren | [MIT](https://github.com/ggml-org/llama.cpp/blob/b11658/LICENSE) |
| Qwen3-4B-Instruct-2507, Q4_K_M GGUF | Interpunctie en opmaak | [Basismodel Apache-2.0](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/blob/main/LICENSE), [quantisatie door bartowski](https://huggingface.co/bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF) |
| whisper.cpp b5454 | Alternatieve lokale herkenner | [MIT](https://github.com/ggml-org/whisper.cpp/blob/b5454/LICENSE) |
| OpenAI Whisper large-v3-turbo, GGML Q5 | Alternatief spraakmodel | [Whisper MIT](https://github.com/openai/whisper/blob/main/LICENSE), [conversiebron](https://huggingface.co/ggerganov/whisper.cpp) |

Parakeet is gemaakt door NVIDIA. De gebruikte GGUF-bestanden zijn gepubliceerde
conversies/quantisaties; Flow Lab traint of wijzigt de gewichten niet. Voor Qwen
wordt de Q4_K_M-quantisatie van bartowski gebruikt. De vastgelegde revisies en
SHA-256-hashes staan in model-lock.json; setup_models.py bevat de downloadkeuzes.

Een eigen installer met meegeleverde CUDA-, Vulkan- of andere runtimebestanden
vereist ook de notices en distributievoorwaarden van die concrete binaries.
De broncode-export doet zo'n binaire herdistributie niet.

## Python-pakketten

De exacte versies staan in requirements.lock.txt. Belangrijke directe onderdelen:

- FastAPI, Starlette, Pydantic, httpx, websockets en comtypes: MIT.
- NumPy en SciPy: BSD-gebaseerd, met aanvullende notices voor gebundelde componenten.
- Pillow: MIT-CMU.
- pystray 0.19.5: [LGPLv3](https://github.com/moses-palmer/pystray/blob/v0.19.5/COPYING.LGPL).
- CPython/Tk hebben hun eigen licenties en worden niet meegeleverd.

pystray is geen eigen MIT-code. Het wordt ongewijzigd als afzonderlijk Python-pakket
geïnstalleerd. Behoud bij eventuele herdistributie de LGPL/GPL-licentieteksten en
de bijbehorende rechten, notices en broncodeverplichtingen; maak er niet stilzwijgend
een onlosmakelijk onderdeel van een gesloten executable van.

OpenAI is een optionele externe API-dienst, geen meegeleverd open model. Gebruikers
leveren hun eigen account en sleutel aan. Wispr Flow-code, merkassets, accountdata
en persoonlijke bibliotheken zijn geen onderdeel van deze broncode-export.

Bronnen en geïnstalleerde pakketmetadata gecontroleerd op 15 oktober 2026.
Dit overzicht geldt voor deze broncodedistributie, niet als volledige binaire SBOM.

Het Flow Lab-woordmerk gebruikt Montserrat. De lettervormen zijn verwerkt in de
meegeleverde logoafbeelding; de app installeert geen extra lettertype.
De SIL Open Font License staat in assets/brand/OFL.txt.

## Optionele Parakeet-ONNX-route

- ONNX ASR 0.12.0: [MIT](https://github.com/istupakov/onnx-asr/blob/main/LICENSE).
- Microsoft ONNX Runtime 1.31.0: [MIT](https://github.com/microsoft/onnxruntime/blob/main/LICENSE).
- FlatBuffers 25.12.19: Apache-2.0; Protocol Buffers 7.36.2: BSD-3-Clause.
- De INT8 ONNX-conversie van Parakeet v3 is gepubliceerd door Ivan Stupakov:
  [model en conversie](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx).
  Oorspronkelijk model: [NVIDIA Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3),
  CC-BY-4.0. De conversie wijzigt formaat en quantisatie; vermeld bij herdistributie
  zowel NVIDIA als de conversiebron en behoud de toepasselijke modellicentie.

De bestanden worden niet in de broncode-export opgenomen. Revisie, hashes en
versies staan in asr-onnx-lock.json en requirements.asr-onnx.txt. De oorspronkelijke
NeMo/ggml-runtime wordt door deze aparte route niet geladen.
