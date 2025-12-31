import io
import os
import platform

import duckdb
import pandas as pd
import uvicorn

from pathlib import Path

from absl import app, flags
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

# Flags
FLAGS = flags.FLAGS
flags.DEFINE_string("game_dir", None, "The root game directory for Cyberpunk 2077.")
flags.DEFINE_integer("port", 8080, "Port to listen on.")

# FastAPI
FASTAPI_APP = FastAPI()
FASTAPI_APP.mount("/static", StaticFiles(directory="static"), name="static")
FASTAPI_TEMPLATES = Jinja2Templates(directory="templates")


@FASTAPI_APP.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    event_df = generate_events()
    events = event_df.to_dict(orient="records")
    last_event = events[-1]
    return FASTAPI_TEMPLATES.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "active_page": "dashboard",
            "last_event": last_event,
            "total_events": len(events),
        },
    )


@FASTAPI_APP.get("/map", response_class=HTMLResponse)
async def map(
    request: Request,
    x: int = None,
    y: int = None,
    z: int = None,
    query: str = None,
    date: str = None,
):
    event_df = generate_events()
    if date:
        map_df = duckdb.sql(
            f"""
            SELECT * FROM event_df WHERE CAST(timestamp AS DATE) = '{date}'
            """
        ).df()
        events = map_df.to_dict(orient="records")

    elif all([x, y, z]):
        print(x, y, z)
    
    else:
        map_df = duckdb.sql(
            """
            SELECT
                *
            FROM event_df 
            WHERE 
                DATE(timestamp) IN (SELECT DATE(MAX(timestamp)) FROM event_df)
            """
        ).df()
        events = map_df.to_dict(orient="records")

    date_df = duckdb.sql(
        """
        SELECT
            timestamp::DATE AS date,
            COUNT(*) AS events,
        FROM event_df 
        GROUP BY 1
        ORDER BY 1
        """
    ).df()
    dates = date_df.to_dict(orient="records")

    height_bounds = (
        duckdb.sql(
            """
        SELECT
            MIN(spatial.z) AS min_height,
            MAX(spatial.z) AS max_height,
        FROM event_df
        GROUP BY ALL
        """
        )
        .df()
        .to_dict(orient="records")
    )[0]

    return FASTAPI_TEMPLATES.TemplateResponse(
        request=request,
        name="map.html",
        context={
            "active_page": "map",
            "x": x,
            "y": y,
            "z": z,
            "query": query or "",
            "events": events,
            "dates": dates,
            "height_bounds": height_bounds,
        },
    )


@FASTAPI_APP.get("/locations", response_class=HTMLResponse)
async def locations(request: Request):
    event_df = generate_events()

    locations = (
        duckdb.sql(
        """
        SELECT
            spatial.district AS location,
            spatial.subDistrict AS name,
            MEDIAN(spatial.x) AS x,
            MEDIAN(spatial.y) AS y,
            MEDIAN(spatial.z) AS z,
            COUNT(*) / SUM(COUNT(*)) OVER () AS time_spent,
        FROM event_df
        WHERE spatial.district != 'Unknown'
        GROUP BY 1, 2
        ORDER BY time_spent DESC
        """
        )
        .df()
        .to_dict(orient="records")
    )

    return FASTAPI_TEMPLATES.TemplateResponse(
        request=request,
        name="locations.html",
        context={
            "active_page": "locations",
            "locations": locations,
        },
    )


@FASTAPI_APP.get("/quests", response_class=HTMLResponse)
async def quests(request: Request):
    event_df = generate_events()

    quests = (
        duckdb.sql(
            """
            SELECT
                identity.lifepath as lifepath,
                narrative.questTitle AS title,
                narrative.questObjective AS objective,
                MIN(timestamp::timestamp) AS first_seen,
                MAX(timestamp::timestamp) AS last_seen,
            FROM event_df
            WHERE narrative.questTitle NOT IN ('None', 'Undiscovered')
            GROUP BY ALL
            ORDER BY first_seen DESC
            """
        )
        .df()
        .to_dict(orient="records")
    )

    return FASTAPI_TEMPLATES.TemplateResponse(
        request=request,
        name="quests.html",
        context={
            "active_page": "quests",
            "quests": quests,
        },
    )


@FASTAPI_APP.get("/insights", response_class=HTMLResponse)
async def insights(request: Request):
    event_df = generate_events()

    # Behavior
    behavior_df = duckdb.sql(
        """
        SELECT
            (SUM(IF(loadout.activeWeapon != 'None', 1, 0)) / COUNT(*)) * 100 AS 'Time spent armed',
            (SUM(IF(loadout.equippedVehicle != 'None', 1, 0)) / COUNT(*)) * 100 AS 'Time spent in vehicle',
            (SUM(IF(status.isCombat::BOOL, 1, 0)) / COUNT(*)) * 100 AS 'Time spent in combat',
            (SUM(IF(status.isDead::BOOL, 1, 0)) / COUNT(*)) * 100 AS 'Time spent clinically dead',
            (SUM(IF(status.isUnderwater::BOOL, 1, 0)) / COUNT(*)) * 100 AS 'Time spent swimming / underwater',
            COUNT(*) AS 'Total time observed',
        FROM event_df
        """
    ).df()
    behavior_metadata = behavior_df.to_dict(orient="records")[0]
    for behavior, metric in behavior_metadata.items():
        if behavior == "Total time observed":
            behavior_metadata[behavior] = (
                f"{metric // 3600}h {(metric % 3600) // 60}m {metric % 60}s"
            )
        else:
            behavior_metadata[behavior] = f"{metric:.2f}%"

    behavior_icons = {
        "Time spent armed": "static/images/icons/behavior/armed.png",
        "Time spent clinically dead": "static/images/icons/behavior/dead.png",
        "Time spent in combat": "static/images/icons/behavior/combat.png",
        "Time spent in vehicle": "static/images/icons/behavior/vehicle.png",
        "Time spent swimming / underwater": "static/images/icons/behavior/swimming.png",
        "Total time observed": "static/images/icons/behavior/camera.png",
    }

    # Top weapons
    weapon_df = duckdb.sql(
        """
        SELECT
            loadout.activeWeapon AS name,
            loadout.activeWeaponIcon AS icon,
            COUNT(*) / SUM(COUNT(*)) OVER() AS usage,
        FROM event_df 
        WHERE 
            REGEXP_MATCHES(loadout.activeWeapon, '^Items.(Craftable|Preset)')
        GROUP BY 1, 2
        ORDER BY 3 DESC
        LIMIT 10;
        """
    ).df()
    favorite_weapons = weapon_df.to_dict(orient="records")

    # Top vehicles
    vehicle_df = duckdb.sql(
        """
        SELECT
            loadout.equippedVehicle AS name,
            loadout.equippedVehicleIcon AS icon,
            COUNT(*) / SUM(COUNT(*)) OVER() AS usage,
        FROM event_df 
        WHERE 
            loadout.equippedVehicle != 'None'
        GROUP BY 1, 2
        ORDER BY 3 DESC
        LIMIT 10;
        """
    ).df()
    favorite_vehicles = vehicle_df.to_dict(orient="records")

    # Top districts
    district_df = duckdb.sql(
        """
        SELECT
            spatial.district AS name,
            spatial.districtIcon AS icon,
            COUNT(*) / SUM(COUNT(*)) OVER() AS usage,
        FROM event_df
        WHERE spatial.district != 'Unknown'
        GROUP BY 1, 2
        ORDER BY 3 DESC;
        """
    ).df()
    favorite_districts = district_df.to_dict(orient="records")

    return FASTAPI_TEMPLATES.TemplateResponse(
        request=request,
        name="insights.html",
        context={
            "active_page": "insights",
            "favorite_districts": favorite_districts,
            "favorite_vehicles": favorite_vehicles,
            "favorite_weapons": favorite_weapons,
            "behavior_metadata": behavior_metadata,
            "behavior_icons": behavior_icons,
        },
    )


@FASTAPI_APP.get("/events", response_class=HTMLResponse)
async def events(request: Request):
    event_df = generate_events()
    total_events = event_df.shape[0]
    event_df = duckdb.sql(
        """
        WITH RECURSIVE event_chain AS (
            (
                SELECT * FROM event_df 
                ORDER BY timestamp ASC 
                LIMIT 1
            )
            
            UNION ALL
            SELECT e.*
            FROM event_df e, event_chain last_e
            WHERE e.timestamp::TIMESTAMP >= last_e.timestamp::TIMESTAMP + INTERVAL 10 MINUTE
            QUALIFY ROW_NUMBER() OVER (ORDER BY e.timestamp::TIMESTAMP ASC) = 1
        )
        SELECT * FROM event_chain ORDER BY timestamp::TIMESTAMP DESC;
    """
    ).df()
    events = event_df.to_dict(orient="records")

    return FASTAPI_TEMPLATES.TemplateResponse(
        request=request,
        name="events.html",
        context={
            "active_page": "events",
            "events": events,
            "total_events": total_events,
        },
    )


@FASTAPI_APP.get("/events/export/csv")
async def export_csv():
    raw_df = generate_events()
    raw_df_data = raw_df.to_dict(orient="records")
    df = pd.json_normalize(data=raw_df_data)
    stream = io.StringIO()
    df.to_csv(stream, index=False)
    response = Response(content=stream.getvalue(), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=agwe_export.csv"
    return response


@FASTAPI_APP.get("/events/export/json")
async def export_json():
    df = generate_events()
    json_data = df.to_json(orient="records")
    response = Response(content=json_data, media_type="application/json")
    response.headers["Content-Disposition"] = "attachment; filename=agwe_export.json"
    return response


# Functions
def validate_game_dir() -> str:
    game_dir = None
    if FLAGS.game_dir:
        # If you're doing some crazy, non-standard thing just pass the
        # directory manually and skip auto-detection.
        game_dir = FLAGS.game_dir
    else:
        home_dir = Path.home()
        match platform.system():
            case "Linux":
                # If you're on Linux, Steam / Proton is the only game in town
                game_dir = (
                    f"{home_dir}/.local/share/Steam/steamapps/common/Cyberpunk 2077"
                )
            case "Windows":
                # If you're on Windows, we assume standard Program Files install
                game_dir = (
                    r"C:\Program Files (x86)\Steam\steamapps\common\Cyberpunk 2077"
                )
            case "Darwin":
                # If you're on MacOS, we assume standard Library paths
                game_dir = f"{home_dir}/Library/Application Support/Steam/steamapps/common/Cyberpunk 2077"
            case _:
                raise ValueError(f"Unsupported platform: {platform.system()}")

    if os.path.exists(game_dir):
        return game_dir


def validate_mod_dir(game_dir: str) -> str:
    mod_dir = None
    if platform.system() == "Windows":
        path_suffix = r"\bin\x64\plugins\cyber_engine_tweaks\mods\PosLogger"
        mod_dir = f"{game_dir}{path_suffix}"

    else:
        mod_dir = f"{game_dir}/bin/x64/plugins/cyber_engine_tweaks/mods/PosLogger"

    if os.path.exists(mod_dir):
        return mod_dir


def get_vehicle_icon(raw_id: str) -> str:
    vid = str(raw_id).replace("Vehicle.", "").lower()
    base_path = "static/images/icons/vehicles/"
    icon_map = [
        # Special
        ("avenger", "Quadra_Type-66_Avenger_Icon_CP2077.png"),
        ("bandit", "Archer_Quartz_Bandit_Icon_CP2077.png"),
        ("cthulhu", "Quadra_Type-66_Cthulhu_Icon_CP2077.png"),
        ("hoon", "Quadra_Type-66_Hoon_Icon_CP2077.png"),
        ("jackie", "Jackie_s_ARCH_Nazaré_Icon_CP2077.png"),
        ("javelina", "Quadra_Type-66_Javelina_Icon_CP2077.png"),
        ("mrhands", "Quadra_Sport_R-7_Sterling_Icon_CP2077PL.png"),
        ("netrunner", "Quadra_Sport_R-7_Charon_Icon_CP2077PL.png"),
        ("player_02", "Quadra_Sport_R-7_Vigilante_Icon_CP2077PL.png"),
        ("scorpion", "Brennan_Apollo_Scorpion_Icon_CP2077.png"),
        ("v_tech", "Quadra_Turbo-R_V-Tech_Icon_CP2077.png"),
        # ARCH
        ("arch_tyger", "ARCH_Nazar%C3%A9_Itsumade_Icon_CP2077.png"),
        ("arch_", "ARCH_Nazar%C3%A9_Icon_CP2077.png"),
        # Archer
        ("archer_hella", "Archer_Hella_EC-D_i360_Icon_CP2077.png"),
        ("archer_quartz", "Archer_Quartz_EC-T2_r660_Icon_CP2077.png"),
        # Brennan
        ("brennan_apollo", "Brennan_Apollo_650-S_Icon_CP2077.png"),
        # Chevillon
        ("chevalier_emperor", "Chevillon_Emperor_620_Ragnar_Icon_CP2077.png"),
        ("chevalier_legatus", "Chevillon_Legatus_450_Aquila_Icon_CP2077.png"),
        ("chevalier_thrax", "Chevillon_Thrax_388_Jefferson_Icon_CP2077.png"),
        # Delamain
        ("delamain", "Delamain_no._21_Icon_CP2077.png"),
        # Herrera
        ("herrera_outlaw", "Herrera_Outlaw_GTS_Icon_CP2077.png"),
        ("herrera_riptide", "Herrera_Riptide_Terrier_Icon_CP2077PL.png"),
        # Mahir
        ("mahir_supron", "Mahir_Supron_FS3-T_Icon_CP2077PL.png"),
        # Makigai
        ("makigai_maimai", "Makigai_MaiMai_P126_Icon_CP2077.png"),
        ("makigai_tanishi", "Makigai_Tanishi_Kuma_Icon_CP2077PL.png"),
        # Militech
        ("hellhound", "Militech_Hellhound_Icon_CP2077PL.png"),
        # Mizutani
        ("mizutani_hozuki", "Mizutani_Hozuki_Hoseki_Icon_CP2077PL.png"),
        ("mizutani_shion_nomad", "Mizutani_Shion_Coyote_Icon_CP2077.png"),
        ("mizutani_shion_player", "Mizutani_Shion_MZ2_Icon_CP2077.png"),
        ("mizutani_shion_targa", "Mizutani_Shion_Targa_MZT_Icon_CP2077.png"),
        # Porsche
        ("porsche_911turbo", "Porsche_911_Turbo_%28930%29_Icon_CP2077.png"),
        (
            "porsche_911turbo_cabrio",
            "Porsche_911_Turbo_Cabriolet_(930)_Icon_CP2077.png",
        ),
        # Quadra
        ("sport_r7", "Quadra_Sport_R-7_Charon_Icon_CP2077PL.png"),
        ("quadra_turbo_r", "Quadra_Turbo-R_V-Tech_Icon_CP2077.png"),
        ("quadra_turbo", "Quadra_Turbo-R_740_Icon_CP2077.png"),
        # Rayfield
        ("rayfield_aerondight", "Rayfield_Aerondight_Guinevere_Icon_CP2077.png"),
        ("rayfield_caliburn", "Rayfield_Caliburn_Icon_CP2077.png"),
        # Thorton
        ("thorton_colby_gt", "Thorton_Colby_CST40_Icon_CP2077.png"),
        ("thorton_colby_pickup", "Thorton_Colby_CX410_Gran_Butte_Icon_CP2077.png"),
        ("thorton_colby", "Thorton_Colby_C125_Icon_CP2077.png"),
        ("thorton_galena_nomad", "Thorton_Galena_Rattler_Icon_CP2077.png"),
        ("thorton_galena", "Thorton_Galena_GA32t_Icon_CP2077.png"),
        # Villefort
        (
            "villefort_alvarado_hearse",
            "Villefort_Alvarado_V4FH_570_Herman_Icon_CP2077PL.png",
        ),
        ("villefort_alvarado", "Villefort_Alvarado_V4F_570_Delegate_Icon_CP2077.png"),
        ("villefort_columbus", "Villefort_Columbus_V340-F_Freight_Icon_CP2077.png"),
        ("villefort_cortes", "Villefort_Cortes_V5000_Valor_Icon_CP2077.png"),
        ("villefort_deleon_sport", "Villefort_Deleon_Vindicator_Icon_CP2077PL.png"),
        ("villefort_deleon", "Villefort_Deleon_V410-S_Coup%C3%A9_Icon_CP2077PL.png"),
        # Yaiba
        ("yaiba_kusanagi", "Yaiba_Kusanagi_CT-3X_Icon_CP2077.png"),
    ]

    for keyword, filename in icon_map:
        if keyword in vid:
            return f"{base_path}{filename}"

    return "None"


def generate_events() -> pd.DataFrame:
    # Validate game configuration
    game_dir = validate_game_dir()
    mod_dir = validate_mod_dir(game_dir=game_dir)
    if not mod_dir and game_dir:
        raise ValueError(
            "Invalid game or mod configuration, consider passing --game_dir flag or re-installing the accompanying mod."
        )

    # Assemble / return events
    event_df = duckdb.sql(
        f"SELECT * FROM read_ndjson('{mod_dir}/*.ndjson') ORDER BY timestamp::TIMESTAMP"
    ).df()

    # Add icons
    district_index = None
    for index, row in event_df.iterrows():
        # District
        district = str(row["spatial"]["district"])
        neighborhood = str(row["spatial"]["subDistrict"])
        valid_districts = {
            "Badlands": "static/images/icons/districts/badlands.png",
            "City Center": "static/images/icons/districts/city_center.png",
            "Dogtown": "static/images/icons/districts/dogtown.png",
            "Heywood": "static/images/icons/districts/heywood.png",
            "Pacifica": "static/images/icons/districts/pacifica.png",
            "Santo Domingo": "static/images/icons/districts/santo_domingo.png",
            "Watson": "static/images/icons/districts/watson.png",
            "Westbrook": "static/images/icons/districts/westbrook.png",
        }

        if district in valid_districts.keys():
            district_index = district
        elif neighborhood in valid_districts.keys():
            district_index = neighborhood

        if district_index:
            row["spatial"]["districtIcon"] = valid_districts[district_index]
        else:
            row["spatial"]["districtIcon"] = "None"

        # Weapon
        weapon = str(row["loadout"]["activeWeapon"])
        if weapon.startswith("Items.Craftable_"):
            weapon = weapon.replace("Items.Craftable_", "").split("_")[-1]
            row["loadout"]["activeWeaponIcon"] = (
                f"static/images/icons/weapons/{weapon}_Default.png"
            )
        elif weapon.startswith("Items.Preset_"):
            weapon = weapon.replace("Items.Preset_", "")
            row["loadout"]["activeWeaponIcon"] = (
                f"static/images/icons/weapons/{weapon}.png"
            )
        else:
            row["loadout"]["activeWeaponIcon"] = "None"

        # Vehicle
        vehicle = str(row["loadout"]["equippedVehicle"])
        row["loadout"]["equippedVehicleIcon"] = get_vehicle_icon(vehicle)

    return event_df


def main(argv):
    del argv

    uvicorn.run(
        FASTAPI_APP,
        host="0.0.0.0",
        port=FLAGS.port,
    )


if __name__ == "__main__":
    app.run(main)
