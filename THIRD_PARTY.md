# Third-party code

## Amazing Hub (`addon/AmazingHub/`) is based on GuildOS

Amazing Hub is built from **GuildOS 1.40.0** (commit `1f9fa9d`) by Chehul (danielcosta42),
https://github.com/danielcosta42/GuildOS, by `tools/rebrand-hub.py`: renamed (so it never shares data, globals or
message prefixes with a real GuildOS install), messages limited to the own guild, group and guild members, and
some features off by default (see `docs/addon/HUB_AUDIT.md`). All credit for the hub's features goes to the GuildOS
author.

GuildOS is released under the MIT License; its licence is kept as `addon/AmazingHub/LICENSE`:

```
MIT License

Copyright (c) 2026 danielcosta42

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Libraries and fonts shipped inside GuildOS (unchanged, each under its own terms)

| Component | Files | Licence |
|---|---|---|
| LibStub | `addon/AmazingHub/Libs/LibStub.lua` | public domain (header) |
| CallbackHandler-1.0, AceComm-3.0 (Ace3 project) | `Libs/` | Ace3 licence (BSD-style) |
| ChatThrottleLib | `Libs/ChatThrottleLib.lua` | public domain (header) |
| LibSerialize, © 2020 Ross Nichols | `Libs/LibSerialize.lua` | MIT (header) |
| LibDeflate, © 2018-2021 Haoqian He | `Libs/LibDeflate.lua` | zlib (header) |
| IBM Plex Sans, IBM Plex Mono | `Media/Fonts/` | SIL Open Font License (`OFL-*.txt` beside them) |
| LibAmzHubMesh (GuildOS's LibChehulMesh, renamed) | `Libs/LibAmzHubMesh.lua` | MIT, as GuildOS |
