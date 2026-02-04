# Rezo Agwe
A second screen experience for Cyberpunk 2077 focusing on mapping and player
stats.

## How does it work?
The "mod" component is a LUA script that hooks into the game engine and outputs
the player's location and core stats to a newline-delimited JSON file. This
happens once per second, which is chatty enough to create a nice animated map,
but slow enough to not impact the game tick / performance.

The "server" component reads this NDJSON output using [DuckDB](https://duckdb.org/)
and renders insights / data in a [FastAPI](https://fastapi.tiangolo.com/)
application. This has been tested with north of 500k events / 60 hours of
playtime and *should* scale to millions of events, but you may want to clear
out the mod root directory (where PosLogger/init.lua lives) of NDJSON files if
you notice it slowing down too much over time.

## Pages / features

| Page | Features | GIF
| --- | --- | --- |
| Subject | Shows core stats, attributes, and quest information for the latest save. | <img src="https://raw.githubusercontent.com/mjcastner/rezo_agwe/refs/heads/main/server/static/images/demo/subject.gif" width="300"> |
| Map | Shows an interactive map of Night City with replays of your game sessions. | <img src="https://raw.githubusercontent.com/mjcastner/rezo_agwe/refs/heads/main/server/static/images/demo/map.gif" width="300"> |
| Locations | Tracks locations your character has visited in the game. | <img src="https://raw.githubusercontent.com/mjcastner/rezo_agwe/refs/heads/main/server/static/images/demo/locations.gif" width="300"> |
| Insights | Metrics and insights about your character, playthrough, and style. | <img src="https://raw.githubusercontent.com/mjcastner/rezo_agwe/refs/heads/main/server/static/images/demo/insights.gif" width="300"> |
| Quests | Tracks quests and objectives that your character has seen in-game. | <img src="https://raw.githubusercontent.com/mjcastner/rezo_agwe/refs/heads/main/server/static/images/demo/quests.gif" width="300"> |
| Archive | Allows you to export all data to JSON or CSV. | <img src="https://raw.githubusercontent.com/mjcastner/rezo_agwe/refs/heads/main/server/static/images/demo/archive.gif" width="300"> |

## Getting started (User)

1. Install the mod component from [Nexus Mods](https://www.nexusmods.com/cyberpunk2077/mods/27268?tab=description).
2. Install [Docker Desktop](https://www.docker.com/)
3. Find your game root directory
    - On Windows (Steam), this defaults to: C:\Program Files (x86)\Steam\steamapps\common\Cyberpunk 2077
    - On Windows (GoG), this defaults to: C:\Program Files (x86)\GOG Galaxy\Games\Cyberpunk 2077
    - On Mac, this defaults to: ~/Library/Application Support/Steam/steamapps/common/Cyberpunk 2077
    - On Linux, this defaults to: ~/.local/share/Steam/steamapps/common/Cyberpunk 2077
    - You may have a non-standard install location, you need to know it to use this.
4. Run the second-screen web server

**Windows (Steam)**
```
docker run \
-p 8080:8080 \
-v "C:\Program Files (x86)\Steam\steamapps\common\Cyberpunk 2077:/game_data:ro" \
ghcr.io/mjcastner/rezo_agwe:latest
```

**Windows (GoG)**
```
docker run \
-p 8080:8080 \
-v "C:\Program Files (x86)\GOG Galaxy\Games\Cyberpunk 2077:/game_data:ro" \
ghcr.io/mjcastner/rezo_agwe:latest
```

**Mac**
```
docker run \
-p 8080:8080 \
-v "$HOME/Library/Application Support/Steam/steamapps/common/Cyberpunk 2077:/game_data:ro" \
ghcr.io/mjcastner/rezo_agwe:latest
```

**Linux**
```
docker run \
-p 8080:8080 \
-v "$HOME/.local/share/Steam/steamapps/common/Cyberpunk 2077:/game_data:ro" \
ghcr.io/mjcastner/rezo_agwe:latest
```

## Getting started (Development)
### 1. Clone the repository

```
git clone https://github.com/mjcastner/rezo_agwe
```

### 2. Install the metrics mod / dependencies

Install the [Cyber Engine Tweaks](https://github.com/maximegmd/CyberEngineTweaks)
mod for Cyberpunk 2077.

Then, copy the contents of the "mod/" folder in your Cyberpunk 2077 game
directory. It will output data as raw NDJSON files alongside the init.lua
file. These NDJSON files are aggregated for CSV / JSON export in the web app.

**Example (Linux)**
```
cp -r mod/bin/ ~/.local/share/Steam/steamapps/common/Cyberpunk\ 2077/
```

### 3. Run the web application
Written with Python 3.12 in mind. Attempts to work with Windows, Mac, and Linux
Steam installs, specify --game_dir if you use a non-standard config.

```
cd server/
pip install -r requirements.txt
python main.py
```

See all args with --help flag.

The server UI will now be available on http://127.0.0.1:8080 by default.

## Feature requests / updates

Pull requests are welcome, please bring your esoteric LUA knowledge.

**Things I'd love to implement**

* Kill tracking
* Per-weapon accuracy
* An actual playthroughID / player UUID to differentiate output logs
  (e.g. each unique lifepath / save combination). This appears to be more
  difficult than originally thought after digging into the SDK.

## Contributions and thanks
This mod would not have been possible without the existing modding community
(WolvenKit, CET, Red4EXT, etc.) who have paved the way for others with tons of
hard work and reverse-engineering hours.

Image icons were extracted from the [Cyberpunk Wiki](https://cyberpunk.fandom.com/wiki/Cyberpunk_Wiki),
while the satellite map was generated with [Tyler](https://github.com/mjcastner/tyler) using a high-resolution map [assembled by u/IcyMind2993 on Reddit](https://www.reddit.com/r/cyberpunkgame/comments/1luor6l/i_created_an_ultraquality_map_of_night_city_from/).

Paweł Sasko is a steely-eyed missile man.