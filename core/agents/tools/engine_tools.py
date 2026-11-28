# -*- coding: utf-8 -*-
"""
core/agents/tools/engine_tools.py — Unity & Unreal Engine Setup + Mechanics Tools.

Allows Kugane's GameEngineAgent to:
  - Detect installed Unity and Unreal Engine editors
  - Import 3D models (.fbx / .glb) into a Unity or Unreal project
  - Generate C# MonoBehaviour gameplay mechanics & Editor auto-setup scripts (Unity)
    or Unreal Editor Python import/spawn scripts + C++ / Blueprint guidance (Unreal)
  - Open the project directly inside Unity or Unreal Editor
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from langchain_core.tools import tool

from config.settings import (
    GENERATED_WORKSPACE,
    UNITY_DEFAULT_PROJECT,
    UNITY_PATH,
    UNREAL_DEFAULT_PROJECT,
    UNREAL_PATH,
)

_UNITY_WORKSPACE = GENERATED_WORKSPACE / "unity"
_UNREAL_WORKSPACE = GENERATED_WORKSPACE / "unreal"


def find_unity_executable() -> str | None:
    if UNITY_PATH and Path(UNITY_PATH).is_file():
        return UNITY_PATH
    which = shutil.which("Unity")
    if which:
        return which

    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    candidates = [
        *sorted((pf / "Unity" / "Hub" / "Editor").glob("*/Editor/Unity.exe"), reverse=True),
        pf / "Unity" / "Editor" / "Unity.exe",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def find_unreal_executable() -> str | None:
    if UNREAL_PATH and Path(UNREAL_PATH).is_file():
        return UNREAL_PATH
    which = shutil.which("UnrealEditor")
    if which:
        return which

    epic = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Epic Games"
    if epic.exists():
        for c in sorted(epic.glob("UE_*/Engine/Binaries/Win64/UnrealEditor.exe"), reverse=True):
            if c.is_file():
                return str(c)
    return None


@tool
def detect_game_engines() -> str:
    """Detect installed Unity Editor and Unreal Engine executables on this Windows PC."""
    unity_exe = find_unity_executable()
    unreal_exe = find_unreal_executable()
    return json.dumps(
        {
            "unity": {"installed": bool(unity_exe), "executable": unity_exe},
            "unreal": {"installed": bool(unreal_exe), "executable": unreal_exe},
        },
        indent=2,
    )


@tool
def setup_unity_scene_and_mechanics(
    project_path: str = "",
    model_path: str = "",
    script_name: str = "KuganeMechanic",
    csharp_code: str = "",
    add_rigidbody: bool = True,
    add_collider: bool = True,
    auto_open_unity: bool = True,
) -> str:
    """
    Prepare a Unity project with a 3D model, a C# MonoBehaviour game-mechanics script,
    and an Editor auto-setup script (Assets/Editor/KuganeAutoSetup.cs) that places the
    model in a scene and attaches the mechanics script, then optionally opens Unity.
    """
    proj_dir = (
        Path(project_path)
        if project_path.strip()
        else (Path(UNITY_DEFAULT_PROJECT) if UNITY_DEFAULT_PROJECT else _UNITY_WORKSPACE / "KuganeUnityProject")
    )
    assets_dir = proj_dir / "Assets"
    models_dir = assets_dir / "KuganeModels"
    scripts_dir = assets_dir / "Scripts"
    editor_dir = assets_dir / "Editor"
    scenes_dir = assets_dir / "Scenes"
    for d in (models_dir, scripts_dir, editor_dir, scenes_dir, proj_dir / "ProjectSettings", proj_dir / "Packages"):
        d.mkdir(parents=True, exist_ok=True)

    manifest = proj_dir / "Packages" / "manifest.json"
    if not manifest.exists():
        manifest.write_text(json.dumps({"dependencies": {}}, indent=2), encoding="utf-8")

    copied_model_rel = ""
    if model_path.strip() and Path(model_path).is_file():
        src = Path(model_path)
        dst = models_dir / src.name
        shutil.copy2(src, dst)
        copied_model_rel = f"Assets/KuganeModels/{src.name}"

    cls_name = re.sub(r"[^A-Za-z0-9_]", "", script_name) or "KuganeMechanic"
    if not csharp_code.strip():
        csharp_code = (
            "using UnityEngine;\n\n"
            f"public class {cls_name} : MonoBehaviour\n"
            "{\n"
            "    public float moveSpeed = 5f;\n"
            "    public float rotateSpeed = 90f;\n\n"
            "    void Update()\n"
            "    {\n"
            "        float h = Input.GetAxis(\"Horizontal\");\n"
            "        float v = Input.GetAxis(\"Vertical\");\n"
            "        transform.Translate(new Vector3(h, 0f, v) * moveSpeed * Time.deltaTime, Space.World);\n"
            "        if (Input.GetKey(KeyCode.Space))\n"
            "            transform.Rotate(Vector3.up, rotateSpeed * Time.deltaTime);\n"
            "    }\n"
            "}\n"
        )
    cs_path = scripts_dir / f"{cls_name}.cs"
    cs_path.write_text(csharp_code.strip() + "\n", encoding="utf-8")

    rb_line = "        if (!go.GetComponent<Rigidbody>()) go.AddComponent<Rigidbody>();\n" if add_rigidbody else ""
    col_line = "        if (!go.GetComponent<Collider>()) go.AddComponent<BoxCollider>();\n" if add_collider else ""
    spawn_block = (
        f'        var prefab = AssetDatabase.LoadAssetAtPath<GameObject>("{copied_model_rel}");\n'
        "        GameObject go = prefab != null ? (GameObject)PrefabUtility.InstantiatePrefab(prefab) : GameObject.CreatePrimitive(PrimitiveType.Cube);\n"
        f'        go.name = "{cls_name}_Actor";\n'
        if copied_model_rel
        else f'        GameObject go = GameObject.CreatePrimitive(PrimitiveType.Cube);\n        go.name = "{cls_name}_Actor";\n'
    )

    editor_cs = (
        "using UnityEditor;\n"
        "using UnityEditor.SceneManagement;\n"
        "using UnityEngine;\n\n"
        "public static class KuganeAutoSetup\n"
        "{\n"
        '    [MenuItem("Kugane/Setup Scene & Mechanics")]\n'
        "    public static void SetupFromCLI()\n"
        "    {\n"
        "        var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);\n"
        f"{spawn_block}"
        f"{col_line}"
        f"{rb_line}"
        f"        if (!go.GetComponent<{cls_name}>()) go.AddComponent<{cls_name}>();\n"
        '        EditorSceneManager.SaveScene(scene, "Assets/Scenes/KuganeScene.unity");\n'
        "        AssetDatabase.Refresh();\n"
        "    }\n"
        "}\n"
    )
    editor_cs_path = editor_dir / "KuganeAutoSetup.cs"
    editor_cs_path.write_text(editor_cs, encoding="utf-8")

    unity_exe = find_unity_executable()
    launched = False
    pid = None
    if auto_open_unity and unity_exe:
        proc = subprocess.Popen(
            [unity_exe, "-projectPath", str(proj_dir), "-executeMethod", "KuganeAutoSetup.SetupFromCLI"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        )
        launched = True
        pid = proc.pid

    return json.dumps(
        {
            "status": "unity_ready_and_launched" if launched else "unity_files_created",
            "project_path": str(proj_dir),
            "model_asset": copied_model_rel or None,
            "mechanic_script": str(cs_path),
            "editor_setup_script": str(editor_cs_path),
            "unity_executable": unity_exe,
            "pid": pid,
            "note": (
                None
                if unity_exe
                else "Unity.exe was not found on this machine. Files were staged in the Unity project; "
                "install Unity or set UNITY_PATH in .env to auto-launch."
            ),
        },
        indent=2,
    )


@tool
def setup_unreal_scene_and_mechanics(
    project_path: str = "",
    model_path: str = "",
    mechanic_name: str = "KuganeMechanic",
    python_setup_code: str = "",
    auto_open_unreal: bool = True,
) -> str:
    """
    Prepare an Unreal Engine project with an imported 3D model, an Unreal Editor
    Python script to import & spawn the mesh with physics/mechanics, and launch
    UnrealEditor if installed.
    """
    proj_dir = (
        Path(project_path)
        if project_path.strip()
        else (Path(UNREAL_DEFAULT_PROJECT) if UNREAL_DEFAULT_PROJECT else _UNREAL_WORKSPACE / "KuganeUnrealProject")
    )
    if proj_dir.suffix.lower() == ".uproject":
        uproject_file = proj_dir
        proj_dir = proj_dir.parent
    else:
        proj_dir.mkdir(parents=True, exist_ok=True)
        existing = list(proj_dir.glob("*.uproject"))
        uproject_file = existing[0] if existing else (proj_dir / f"{proj_dir.name}.uproject")
        if not uproject_file.exists():
            uproject_file.write_text(
                json.dumps({"FileVersion": 3, "EngineAssociation": "", "Category": "", "Description": "Kugane UE Project"}, indent=2),
                encoding="utf-8",
            )

    content_models = proj_dir / "Content" / "KuganeModels" / "Source"
    scripts_dir = proj_dir / "Scripts"
    content_models.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    copied_model = ""
    if model_path.strip() and Path(model_path).is_file():
        src = Path(model_path)
        dst = content_models / src.name
        shutil.copy2(src, dst)
        copied_model = str(dst)

    clean_name = re.sub(r"[^A-Za-z0-9_]", "", mechanic_name) or "KuganeMechanic"
    if not python_setup_code.strip():
        fbx_posix = Path(copied_model).as_posix() if copied_model else ""
        python_setup_code = (
            "import unreal\n\n"
            f'model_src = "{fbx_posix}"\n'
            'dest_path = "/Game/KuganeModels"\n'
            "if model_src:\n"
            "    task = unreal.AssetImportTask()\n"
            "    task.filename = model_src\n"
            "    task.destination_path = dest_path\n"
            "    task.automated = True\n"
            "    task.save = True\n"
            "    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])\n"
            "    for asset_path in task.imported_object_paths:\n"
            "        mesh = unreal.EditorAssetLibrary.load_asset(asset_path)\n"
            "        if mesh:\n"
            "            actor = unreal.EditorLevelLibrary.spawn_actor_from_object(mesh, unreal.Vector(0, 0, 100))\n"
            "            if actor and hasattr(actor, 'static_mesh_component'):\n"
            "                actor.static_mesh_component.set_simulate_physics(True)\n"
            f'                actor.set_actor_label("{clean_name}_Actor")\n'
        )
    py_path = scripts_dir / f"{clean_name}_setup.py"
    py_path.write_text(python_setup_code.strip() + "\n", encoding="utf-8")

    unreal_exe = find_unreal_executable()
    launched = False
    pid = None
    if auto_open_unreal and unreal_exe:
        proc = subprocess.Popen(
            [unreal_exe, str(uproject_file), f"-ExecutePythonScript={py_path}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        )
        launched = True
        pid = proc.pid

    return json.dumps(
        {
            "status": "unreal_ready_and_launched" if launched else "unreal_files_created",
            "uproject_path": str(uproject_file),
            "model_source": copied_model or None,
            "python_setup_script": str(py_path),
            "unreal_executable": unreal_exe,
            "pid": pid,
            "note": (
                None
                if unreal_exe
                else "UnrealEditor.exe was not found on this machine. Files were staged in the Unreal project; "
                "set UNREAL_PATH in .env or open the .uproject with Unreal Engine."
            ),
        },
        indent=2,
    )
