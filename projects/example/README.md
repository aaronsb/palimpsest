# Example project

A project is a directory — it does not have to live here. This one carries a
`config.json` and nothing else, so the repo shows the shape without shipping a
document.

To start a real one:

```bash
mkdir -p ~/Palimpsest/my-doc/source
cp projects/example/config.json ~/Palimpsest/my-doc/config.json
cp mydocument.pdf ~/Palimpsest/my-doc/source/
$EDITOR ~/Palimpsest/my-doc/config.json      # title, langs, domain_context, grid
```

Then run the pipeline against that path:

```bash
engine/.venv/bin/python engine/scripts/extract.py ~/Palimpsest/my-doc
```

`source/` and `artifacts/` are gitignored wherever a project lives. Versioning a
project's artifacts is a matter for that project's own directory, not this repo.
