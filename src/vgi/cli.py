"""vgi command line."""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

import typer
from rich.table import Table

from . import __version__
from .config import ConfigLoader, config_from_content, load_secrets, load_yaml
from .core.job import Job
from .core.logging import console
from .core.runner import PLAN_STAGES, RENDER_STAGES, run_stages, slice_stages
from .core.stage import RunContext

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Local AI video pipeline for Instagram Reels.")
corpus_app = typer.Typer(help="Corpus management.")
models_app = typer.Typer(help="Model files for ComfyUI.")
app.add_typer(corpus_app, name="corpus")
app.add_typer(models_app, name="models")


# ---------- helpers ----------
def find_root() -> Path:
    env = os.environ.get("VGI_ROOT")
    if env:
        return Path(env)
    p = Path.cwd()
    for cand in (p, *p.parents):
        if (cand / "configs" / "global.yaml").exists():
            return cand
    raise typer.BadParameter("not inside a vgi project (no configs/global.yaml found); set VGI_ROOT")


def default_env() -> str:
    if os.environ.get("VGI_ENV"):
        return os.environ["VGI_ENV"]
    if platform.system() == "Darwin":
        return "mac_m5max"
    try:
        n = len(subprocess.run(["nvidia-smi", "--list-gpus"], capture_output=True, text=True, timeout=10).stdout.splitlines())
    except Exception:  # noqa: BLE001
        n = 0
    return "linux_4x4090" if n >= 4 else "linux_2x3090"


def jobs_root(root: Path) -> Path:
    g = load_yaml(root / "configs" / "global.yaml")
    return root / g.get("outputs_dir", "outputs/jobs")


def make_ctx(root: Path, job: Job, env: str | None, dry_run: bool = False, force: bool = False,
             scene: list[int] | None = None, reseed: int = 0, overrides: list[str] | None = None) -> RunContext:
    env = env or job.manifest.env_used or default_env()
    env_raw = load_yaml(root / "configs" / "env" / f"{env}.yaml")
    pricing_p = root / "configs" / "pricing.yaml"
    content = job.manifest.content_config
    if overrides:
        from .config.loader import _apply_override, _parse_override  # noqa: PLC0415

        for item in overrides:
            path, value = _parse_override(item)
            _apply_override(content, path, value)
    cfg = config_from_content(content, env_raw, load_yaml(pricing_p) if pricing_p.exists() else {})
    job.manifest.env_used = env
    job.save()
    return RunContext(root=root, job=job, cfg=cfg, secrets=load_secrets(), dry_run=dry_run, force=force,
                      scene_filter=scene or None, reseed=reseed)


def _job(root: Path, ref: str) -> Job:
    try:
        return Job.find(jobs_root(root), ref)
    except (FileNotFoundError, ValueError) as e:
        raise typer.BadParameter(str(e)) from e


# ---------- commands ----------
@app.command()
def version() -> None:
    console.print(f"vgi {__version__}")


@app.command()
def new(topic: str = typer.Option(..., help="configs/topics/<topic>.yaml"),
        subject: str = typer.Option(..., help='e.g. "Battle of Badr" or a meme hint'),
        env: str = typer.Option(None, help="configs/env/<env>.yaml (auto-detected)"),
        set_: list[str] = typer.Option(None, "--set", help="override key.path=value, e.g. stages.video.steps=20")) -> None:
    """Create a job folder with a frozen content config."""
    root = find_root()
    env = env or default_env()
    cfg = ConfigLoader(root).load(env, topic, set_ or [])
    job = Job.create(jobs_root(root), topic, subject, cfg.content())
    job.manifest.env_used = env
    job.save()
    console.print(f"[green]created[/green] {job.id}  →  {job.path}")


@app.command()
def plan(job: str, env: str = None, dry_run: bool = False, force: bool = False,
         scene: list[int] = typer.Option(None, help="only these scene ids (keyframes)")) -> None:
    """Part A: research → script → keyframes → storyboard preview."""
    root = find_root()
    j = _job(root, job)
    ctx = make_ctx(root, j, env, dry_run, force, scene)
    run_stages(ctx, PLAN_STAGES)
    console.print(f"[green]planned[/green] preview: {j.dir('storyboard') / 'preview.html'}")


@app.command()
def preview(job: str, open_: bool = typer.Option(True, "--open/--no-open")) -> None:
    """Show (and open) the storyboard preview."""
    root = find_root()
    j = _job(root, job)
    p = j.dir("storyboard") / "preview.html"
    if not p.exists():
        raise typer.BadParameter("no preview yet; run `vgi plan`")
    console.print(str(p))
    if open_:
        webbrowser.open(p.as_uri())


@app.command()
def pick(job: str, scene: int, candidate: int) -> None:
    """Choose keyframe candidate for a scene (writes keyframe_choice into scene_plan.json)."""
    root = find_root()
    j = _job(root, job)
    plan_ = json.loads(j.scene_plan_path.read_text(encoding="utf-8"))
    for s in plan_["scenes"]:
        if s["id"] == scene:
            s["keyframe_choice"] = candidate
            break
    else:
        raise typer.BadParameter(f"scene {scene} not found")
    j.scene_plan_path.write_text(json.dumps(plan_, indent=2, ensure_ascii=False), encoding="utf-8")
    if j.invalidate_if_plan_changed():
        console.print("[yellow]plan changed after approval → state reset to planned; approve again[/yellow]")
    console.print(f"scene {scene} → candidate {candidate}")


@app.command()
def approve(job: str) -> None:
    """Approve the current scene plan (records its hash); required before render."""
    root = find_root()
    j = _job(root, job)
    j.approve()
    console.print(f"[green]approved[/green] {j.id} (plan hash {j.manifest.approved_plan_hash})")


@app.command()
def render(job: str = typer.Argument(None), env: str = None, dry_run: bool = False, force: bool = False,
           scene: list[int] = typer.Option(None), reseed: int = typer.Option(0, help="bump seed_base for --scene"),
           all_approved: bool = typer.Option(False, "--all-approved", help="render every approved job")) -> None:
    """Part B: tts → video → music → captions → assemble. Requires an approved plan."""
    root = find_root()
    targets = [Job(p.parent) for p in jobs_root(root).glob("*/manifest.json")] if all_approved else [_job(root, job)]
    for j in targets:
        if all_approved and j.manifest.state != "approved":
            continue
        if j.invalidate_if_plan_changed():
            console.print(f"[yellow]{j.id}: plan edited after approval; re-approve[/yellow]")
            continue
        if not j.is_approved() and not dry_run:
            raise typer.BadParameter(f"{j.id} is not approved (state={j.manifest.state}); run `vgi approve`")
        ctx = make_ctx(root, j, env, dry_run, force or bool(scene), scene, reseed)
        run_stages(ctx, RENDER_STAGES)
        console.print(f"[green]rendered[/green] {j.dir('assemble') / 'final.mp4'}")


@app.command()
def qa(job: str, env: str = None, override: bool = False, reason: str = "") -> None:
    """Spec + policy checks → qa_report.md. --override records a reason and allows export."""
    root = find_root()
    j = _job(root, job)
    ctx = make_ctx(root, j, env, force=True)
    run_stages(ctx, ["qa"])
    if override and j.manifest.state == "qa_failed":
        if not reason:
            raise typer.BadParameter("--override needs --reason")
        j.record("qa").notes.append(f"OVERRIDE: {reason}")
        j.set_state("qa_passed")
        console.print(f"[yellow]QA overridden:[/yellow] {reason}")
    console.print(str(j.dir("qa") / "qa_report.md"))


@app.command()
def export(job: str, env: str = None) -> None:
    """Write final deliverables (mp4, cover.jpg, caption.txt, metadata.json)."""
    root = find_root()
    j = _job(root, job)
    ctx = make_ctx(root, j, env, force=True)
    run_stages(ctx, ["export"])
    console.print(f"[green]exported[/green] {j.dir('export')}")


@app.command()
def run(job: str, env: str = None, from_: str = typer.Option(None, "--from"), until: str = typer.Option(None, "--until"),
        dry_run: bool = False, auto_approve: bool = False, force: bool = False) -> None:
    """Run a slice of the full DAG. --dry-run implies --auto-approve and stub backends."""
    root = find_root()
    j = _job(root, job)
    names = slice_stages(from_, until)
    ctx = make_ctx(root, j, env, dry_run, force)
    for n in names:
        if n == "tts" and not j.is_approved():
            if dry_run or auto_approve:
                j.approve()
                console.print("[yellow]auto-approved[/yellow]")
            else:
                raise typer.BadParameter("plan not approved; run `vgi approve` or pass --auto-approve")
        if j.invalidate_if_plan_changed():
            raise typer.BadParameter("plan changed after approval; re-approve")
        run_stages(ctx, [n])
    console.print(f"[green]done[/green] state={j.manifest.state}")


@app.command()
def jobs() -> None:
    """List jobs."""
    root = find_root()
    t = Table("job", "topic", "subject", "state", "cost $", "env")
    for p in sorted(jobs_root(root).glob("*/manifest.json")):
        m = Job(p.parent).manifest
        t.add_row(m.job_id, m.topic, m.subject, m.state, f"{m.total_cost_usd:.3f}", m.env_used)
    console.print(t)


@app.command()
def logs(job: str, stage: str = None, tail: int = 40) -> None:
    root = find_root()
    j = _job(root, job)
    files = [j.log_dir / f"{stage}.jsonl"] if stage else sorted(j.log_dir.glob("*.jsonl"))
    for f in files:
        if f.exists():
            console.rule(f.name)
            for line in f.read_text(encoding="utf-8").splitlines()[-tail:]:
                console.print(line, markup=False)


@app.command()
def doctor(env: str = None) -> None:
    """Check tools, endpoints, models, memory and credentials for an environment."""
    root = find_root()
    env = env or default_env()
    loader = ConfigLoader(root)
    t = Table("check", "status", "detail")

    def row(name: str, ok: bool | None, detail: str = "") -> None:
        t.add_row(name, "[green]ok[/green]" if ok else ("[yellow]warn[/yellow]" if ok is None else "[red]missing[/red]"), detail)

    from .media.ffmpeg import ffmpeg_bin, ffprobe_bin, has_libass

    row("ffmpeg", Path(ffmpeg_bin()).exists(), ffmpeg_bin())
    row("ffprobe", Path(ffprobe_bin()).exists(), ffprobe_bin())
    row("libass (captions)", has_libass(), "" if has_libass() else "install ffmpeg-full (brew) or ffmpeg with --enable-libass")
    try:
        cfg = loader.load(env, loader.available("topics")[0])
        row("config", True, f"env={env} topics={loader.available('topics')}")
    except Exception as e:  # noqa: BLE001
        row("config", False, str(e))
        console.print(t)
        raise typer.Exit(1)
    sec = load_secrets()
    row("ANTHROPIC_API_KEY", True if sec.has_claude() else None, "set" if sec.has_claude() else "missing → stub LLM")
    comfy = cfg.env.comfy
    if comfy.endpoints:
        from .backends.comfy_client import ComfyClient

        for e in comfy.endpoints:
            c = ComfyClient(e, timeout_s=3)
            ok = c.healthy()
            detail = ""
            if ok:
                try:
                    st = c.system_stats()
                    dev = st.get("devices", [{}])[0]
                    detail = f"{dev.get('name', '')} vram_free={dev.get('vram_free', 0) / 2**30:.1f} GB"
                except Exception:  # noqa: BLE001
                    pass
            row(f"comfy {e}", ok, detail or "unreachable (video falls back to ken_burns)")
    else:
        row("comfy endpoints", None, "none configured → video uses ken_burns")
    ram = cfg.env.hardware.get("ram_gb")
    if comfy.dual_instance:
        row("dual ComfyUI instances", (ram or 0) >= 64, f"ram_gb={ram} (needs >= 64)")
    mac = platform.system() == "Darwin"
    checks = [("kokoro", "tts"), ("cv2", "qa"), ("whisperx", "captions")] + ([("mlx_audio", "mac"), ("mflux", "mac")] if mac else [])
    for mod, extra in checks:
        try:
            __import__(mod)
            row(mod, True)
        except ImportError:
            row(mod, None, f"uv sync --extra {extra}")
    if mac:
        row("mflux-generate", shutil.which("mflux-generate") is not None, shutil.which("mflux-generate") or "uv sync --extra mac")
    if platform.system() == "Darwin":
        try:
            mem = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).decode()) // 2**30
            row("unified memory", mem >= 32, f"{mem} GB")
        except Exception:  # noqa: BLE001
            pass
    else:
        row("nvidia-smi", shutil.which("nvidia-smi") is not None)
    wf = root / "comfy" / "workflows"
    row("workflow templates", None if not list(wf.glob("*.json")) else True, ", ".join(p.stem for p in wf.glob("*.json")) or "none exported yet")
    console.print(t)


@corpus_app.command("wikipedia")
def corpus_wikipedia(title: str, topic: str = "islamic_battles") -> None:
    """Fetch a Wikipedia article (plain text, CC BY-SA 4.0) into the topic corpus with an attribution header."""
    import httpx

    root = find_root()
    tcfg = load_yaml(root / "configs" / "topics" / f"{topic}.yaml")
    out_dir = root / tcfg.get("corpus_dir", "data/corpus/islamic")
    out_dir.mkdir(parents=True, exist_ok=True)
    r = httpx.get("https://en.wikipedia.org/w/api.php", params={"action": "query", "prop": "extracts|info", "explaintext": 1,
                                                                 "redirects": 1, "inprop": "url", "titles": title, "format": "json"},
                  headers={"User-Agent": os.environ.get("VGI_HTTP_UA", "vgi-corpus/0.1 (+https://github.com/saikhu/video_gen_insta; research tool) python-httpx")}, timeout=30, follow_redirects=True)
    r.raise_for_status()
    pages = r.json()["query"]["pages"]
    page = next(iter(pages.values()))
    if "extract" not in page:
        raise typer.BadParameter(f"no article for {title!r}")
    slug = "".join(c if c.isalnum() else "_" for c in page["title"]).strip("_").lower()
    out = out_dir / f"wikipedia_{slug}.md"
    out.write_text(f"---\ntitle: Wikipedia: {page['title']}\nlicense: CC BY-SA 4.0\nurl: {page.get('fullurl', '')}\n---\n\n"
                   + page["extract"], encoding="utf-8")
    console.print(f"[green]saved[/green] {out} ({len(page['extract'])} chars)")


@corpus_app.command("gutenberg")
def corpus_gutenberg(ebook_id: int, title: str = typer.Option(..., help="human title for the header"),
                     topic: str = "islamic_battles") -> None:
    """Fetch a public-domain Project Gutenberg plain-text ebook into the topic corpus."""
    import httpx

    root = find_root()
    tcfg = load_yaml(root / "configs" / "topics" / f"{topic}.yaml")
    out_dir = root / tcfg.get("corpus_dir", "data/corpus/islamic")
    out_dir.mkdir(parents=True, exist_ok=True)
    ua = os.environ.get("VGI_HTTP_UA", "vgi-corpus/0.1 (+https://github.com/saikhu/video_gen_insta; research tool) python-httpx")
    text = None
    for url in (f"https://www.gutenberg.org/cache/epub/{ebook_id}/pg{ebook_id}.txt",
                f"https://www.gutenberg.org/files/{ebook_id}/{ebook_id}-0.txt"):
        r = httpx.get(url, headers={"User-Agent": ua}, timeout=60, follow_redirects=True)
        if r.status_code == 200 and len(r.text) > 1000:
            text = r.text
            break
    if text is None:
        raise typer.BadParameter(f"could not download ebook {ebook_id}")
    # strip the Gutenberg header/footer boilerplate
    start = text.find("*** START OF")
    end = text.find("*** END OF")
    body = text[text.find("\n", start) + 1 if start != -1 else 0: end if end != -1 else None]
    slug = "".join(c if c.isalnum() else "_" for c in title).strip("_").lower()[:60]
    out = out_dir / f"gutenberg_{ebook_id}_{slug}.md"
    out.write_text(f"---\ntitle: {title}\nlicense: public domain (Project Gutenberg #{ebook_id})\n"
                   f"url: https://www.gutenberg.org/ebooks/{ebook_id}\n---\n\n" + body.strip() + "\n", encoding="utf-8")
    console.print(f"[green]saved[/green] {out} ({len(body)} chars)")


@models_app.command("list")
def models_list() -> None:
    root = find_root()
    p = root / "comfy" / "models.yaml"
    data = load_yaml(p) if p.exists() else {}
    t = Table("name", "repo", "file", "dest")
    for m in data.get("models", []):
        t.add_row(m["name"], m["repo"], m["file"], m["dest"])
    console.print(t)


@models_app.command("pull")
def models_pull(env: str = None, only: str = typer.Option(None, help="model name filter"),
                include_optional: bool = typer.Option(False, "--include-optional", help="also pull entries marked optional")) -> None:
    """Download model files listed in comfy/models.yaml into the env's models_dir (needs huggingface_hub)."""
    root = find_root()
    env = env or default_env()
    envc = load_yaml(root / "configs" / "env" / f"{env}.yaml")
    models_dir = Path(os.environ.get("MODELS_DIR") or envc.get("comfy", {}).get("models_dir") or "models")
    if not models_dir.is_absolute():
        models_dir = root / models_dir
    data = load_yaml(root / "comfy" / "models.yaml")
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise typer.BadParameter("pip install huggingface_hub (or: uv pip install huggingface_hub)")
    failed: list[str] = []
    total = sum(float(m.get("gb", 0)) for m in data.get("models", []) if (include_optional or not m.get("optional")))
    console.print(f"models dir: {models_dir}  (~{total:.0f} GB selected)")
    for m in data.get("models", []):
        if only and only not in m["name"]:
            continue
        if m.get("optional") and not include_optional:
            continue
        dest = models_dir / m["dest"]
        dest.mkdir(parents=True, exist_ok=True)
        final = dest / Path(m["file"]).name
        if final.exists():
            console.print(f"[dim]have[/dim] {final.name}")
            continue
        console.print(f"↓ {m['repo']}/{m['file']} ({m.get('gb', '?')} GB) → {final}")
        try:
            got = Path(hf_hub_download(m["repo"], m["file"], local_dir=str(dest), token=os.environ.get("HF_TOKEN") or None))
            if got.resolve() != final.resolve():      # hf keeps the repo subpath under local_dir; flatten it
                got.replace(final)
                for parent in got.parents:
                    if parent == dest or not parent.is_relative_to(dest):
                        break
                    try:
                        parent.rmdir()
                    except OSError:
                        break
        except Exception as e:  # noqa: BLE001  keep going; report at the end
            console.print(f"[red]failed[/red] {m['name']}: {str(e)[:200]}")
            failed.append(m["name"])
    if failed:
        console.print(f"[yellow]{len(failed)} download(s) failed:[/yellow] {', '.join(failed)} — check names in comfy/models.yaml")
        raise typer.Exit(1)
    console.print("[green]done[/green]")


if __name__ == "__main__":
    sys.exit(app())
