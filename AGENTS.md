# Safe Cycle - Repository Instructions

## Communication

- Respond to the user in German.
- Explain technical decisions briefly and clearly.
- Use English names for code identifiers and German comments and docstrings.

## Project Overview

Safe Cycle is a Python-based bicycle safety system running on a Radxa Dragon
Q6A. The MVP combines camera and sensor data to detect critical overtaking
events, store evidence, and display completed rides in a local post-ride
dashboard.

The main components are:

- A rear-facing radar detects approaching vehicles and their relative speed.
- Side-facing ToF sensors measure the actual lateral overtaking distance.
- GPS provides position and bicycle speed.
- The IMU provides acceleration data for later features such as crash
  detection.
- YOLO detects and tracks vehicles in the camera image.
- MQTT will connect sensor nodes with the central processing logic.
- The dashboard reads completed ride logs and associated evidence images.

## Repository Structure

- `src/sensors/`: Hardware access and MQTT publishing for radar, ToF, GPS,
  and IMU.
- `src/vision/`: Camera input, YOLO inference, object tracking, and model
  files.
- `src/core/`: Sensor synchronization, event detection, bounded buffers,
  and ride logging.
- `src/dashboard/`: Local post-ride dashboard.
- `src/shared/`: Shared interfaces such as MQTT payload dataclasses.
- `tests/`: Mirrors the structure of `src/`.
- `hardware_docs/`: Schematics, construction files, and hardware notes.

Keep these responsibilities separate:

- Sensor nodes publish only their own readings. They must not import the
  central logger or other sensor nodes.
- Vision code reports detections and tracking results. It must not decide
  whether an overtaking event is a violation or write ride logs.
- Core code combines vision and sensor data and owns the event and logging
  decisions.
- Shared data structures belong in `src/shared/`.

## Coding Style

- Prefer simple, explicit, and understandable code.
- Avoid unnecessary abstractions, design patterns, and dependencies.
- Use English names for files, modules, classes, functions, variables, and
  constants.
- Use German comments and docstrings to explain non-obvious behavior.
- Add comments only when they provide information that the code itself does
  not make clear.
- Follow PEP 8 and the Ruff configuration in `pyproject.toml`.
- Add type hints to all function parameters and return values.
- Use short German docstrings. Parameters may be documented with concise
  `:param name:` lines.
- Add a short example to a docstring when the API usage or data conversion is
  not obvious. Do not add examples to trivial functions.
- Use doctest syntax for executable examples: write the call after `>>>` and
  the exact expected output on the next line.
- Use a plain example without `>>>` only when it is explanatory and cannot be
  executed meaningfully. Keep all examples small and readable.
- Use dataclasses for the agreed MQTT payload structures.
- Use `pathlib.Path` for filesystem paths, converting paths to strings only
  when serializing them to JSON.
- Keep hardware access separate from parsing and business logic so that the
  latter can be tested without physical hardware.
- Prefer pure functions for parsing, unit conversions, timestamp matching,
  threshold checks, and event decisions. A pure function returns the same
  result for the same input and does not modify external state.
- Keep unavoidable side effects such as sensor reads, MQTT communication,
  camera access, and file writes in small boundary functions. Pass their data
  into pure functions instead of mixing I/O with decision logic.

## Dependencies

Use `uv` for all Python dependency management.

- Synchronize the environment with `uv sync`.
- Add a package with `uv add PACKAGE`.
- Do not use `pip install` for project dependencies.
- Commit both `pyproject.toml` and `uv.lock` when dependencies change.
- Do not add large libraries unless they solve a concrete project
  requirement.

## Testing

- Write tests with Pytest for every implemented function and relevant edge
  case.
- Mirror production modules under `tests/`.
- Mock hardware, serial ports, MQTT clients, cameras, and clocks where needed.
- Tests must not require connected sensors or Radxa-specific hardware in the
  normal CI environment.
- Keep hardware integration tests separate from normal unit tests.
- A bug fix should include a regression test when practical.

Before committing or pushing, run all of these commands from the repository
root:

```bash
uv run ruff check .
uv run mypy
uv run pytest
```

Do not commit or push while any of these checks fail.

## Git Workflow

- Do not develop directly on `main`.
- Use focused branches such as `feature/radar`, `feature/vision`, or
  `chore/initial-setup`.
- Check `git status` before staging files.
- Do not commit local environments, IDE settings, caches, model weights,
  ride data, or evidence images.
- Keep commits focused and write clear commit messages in German.
- Open a pull request when a feature is complete and the required checks pass.
- Do not commit or push unless explicitly requested.

## Implementation Boundaries

- Do not invent hardware protocols. Implement them from the relevant
  datasheet and document important units or byte conversions.
- Preserve the agreed payload field names and units unless the interface
  change is coordinated across publishers, consumers, and tests.
- Radar and ToF serve different purposes and must remain separate data
  sources.
- Store images as files and use relative string paths in ride JSON data.
- Avoid frequent filesystem writes for live sensor communication. Use MQTT
  and in-memory state or bounded buffers.
- Keep generated data and large model files out of Git.
