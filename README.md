# Mnemo8 MVP

A non-functional, terminal-based personal assistant CLI to validate configuration models and terminal UX.

## Installation

Ensure you have Python 3.11+ installed.
From the root of this repository, run the following command to install the package in "editable" mode:

```bash
pip install -e .
```

## Usage

Run the assistant from any directory:

```bash
mnemo8
```

It will look for an `AGENTS.md` file and a `skills/` folder in your current working directory.

## Development

Because the project is installed using `-e` (editable mode), any changes you make to the source code in the `mnemo8/` directory are **immediately reflected** the next time you run the `mnemo8` command. 

You do not need to re-run `pip install` or "refresh" the application after making a code change. Just exit the CLI (by typing `exit`) and start it again.