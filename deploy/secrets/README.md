# Docker Secret Files

Production Compose reads three host files:

```text
deploy/secrets/django-secret-key
deploy/secrets/postgres-password
deploy/secrets/frontend-credentials.json
```

They are gitignored. Each file must be a regular file owned by numeric UID 0,
dedicated secret-reader GID 10004, and mode `0440`, inside the private
`deploy/secrets/` directory owned by root with mode `0700`. Local file-backed
Compose preserves host metadata; it does not apply `uid`, `gid`, or `mode` from a
secret declaration. Only services with both an explicit secret mount and
supplemental GID 10004 can read a file. Never make a source world-readable.

## First provisioning

Creating the host group and these root-owned files is an R5 host responsibility,
not an action performed by this repository. On the intended VPS, first run
`getent group 10004` and stop if that numeric GID already belongs to another
purpose. When it is unused, the reviewed host operation creates it explicitly:

```bash
sudo groupadd --gid 10004 libretiles-secrets
getent group 10004
```

The second command must report `libretiles-secrets` with numeric GID 10004.
From the reviewed repository checkout, create the private directory:

```bash
sudo install -d -o root -g root -m 0700 deploy/secrets
```

For each exact final name, create a temporary file in that same directory. This
example uses `sudoedit`, so the value is entered in an editor and never placed in
a command argument or shell history:

```bash
secret_name=django-secret-key
temporary=$(sudo mktemp --tmpdir=deploy/secrets ".${secret_name}.XXXXXX")
sudoedit "$temporary"
sudo chown 0:10004 "$temporary"
sudo chmod 0440 "$temporary"
sudo stat -c '%n %u:%g %a %F' "$temporary"
sudo mv -T "$temporary" "deploy/secrets/$secret_name"
sudo stat -c '%n %u:%g %a %F' "deploy/secrets/$secret_name"
unset temporary secret_name
```

Repeat with `postgres-password` and `frontend-credentials.json`. Every metadata
line must end in `0:10004 440 regular file`; stop if it does not. Verify the
private directory separately:

```bash
sudo stat -c '%n %u:%g %a %F' deploy/secrets
```

It must end in `0:0 700 directory`. These commands reveal metadata only. Do not
use `echo`, a command argument, an environment variable, or a sourced shell file
to deliver a value.

The Django key must satisfy the checks documented in `backend/.env.example`.
The PostgreSQL file contains one password line. Frontend credentials are one
JSON object whose optional keys are shown by the committed example. `{}`
deliberately starts the UI without an external AI credential.

## Rotation

Stage a replacement with the same `mktemp` → private editor → `chown 0:10004` →
`chmod 0440` → metadata verification sequence, then use `mv -T` for an atomic
same-directory rename over the exact final path. Recreate every Compose service
that consumes that file so its read-only bind mount receives the new inode, and
verify source and target metadata plus service health afterward.

Replacing `postgres-password` alone does not change the password stored in an
existing PostgreSQL cluster. Coordinate the database-role change and the atomic
file replacement as one separately reviewed, recoverable host operation before
recreating PostgreSQL, backend-init, backend, and db-tools. Rotating the Django
key invalidates signed sessions. Provider credential rotation requires frontend
recreation. Retain the prior value only in the approved secret/recovery system,
never as another file in this directory.

The `.example` files are non-operational documentation only. Copying their
placeholder values must fail production startup.
