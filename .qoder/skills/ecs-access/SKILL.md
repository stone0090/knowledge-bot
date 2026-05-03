---
name: ecs-access
description: Connect to and operate the project's CentOS 7.6 ECS server that hosts the Vault Git bare repo. Covers the SSH alias, server paths, known OS compatibility pitfalls (git 1.8, ripgrep on CentOS 7), and security posture. Use whenever the user asks to run commands on the server, clone/push the vault, diagnose SSH issues, or deploy to ECS.
---

# ECS Access

This project uses a single ECS (Aliyun, CentOS 7.6, IP `121.196.26.127`, SSH port `4500`) as the Git bare server for the Vault. A local SSH alias `kb` has been configured via `scripts/setup_ssh_keyless.sh`.

## Golden rule

**Always use the `kb` alias.** Never write the full `ssh -p 4500 root@121.196.26.127` form in commands, scripts, docs, or suggestions.

```bash
ssh kb                                    # interactive login
ssh kb '<cmd>'                            # one-shot remote command
git clone kb:/opt/vault-bare.git <path>   # clone the vault
scp <file> kb:/tmp/                       # upload
```

The alias is defined in the user's `~/.ssh/config`:

```
Host kb
    HostName 121.196.26.127
    Port 4500
    User root
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

If `ssh kb` fails with "Could not resolve hostname" or prompts for a password, the alias is missing — rerun `bash scripts/setup_ssh_keyless.sh` in the project root.

## Server layout

| Path | Role |
|---|---|
| `/opt/vault-bare.git` | **Central bare repo** — the single source of truth. Default branch: `master`. HEAD is `refs/heads/master`. Never `git commit` here. |
| `/opt/vault` | **Working copy on the server** — `origin` points to `/opt/vault-bare.git`. Safe to `git pull` / inspect, avoid committing from here. |
| `/usr/local/bin/rg` | Statically linked ripgrep 14.x (installed via `scripts/ecs_bootstrap_vault.sh`). |

To re-bootstrap a blank ECS (rare), run `scripts/ecs_bootstrap_vault.sh` locally and pipe it:

```bash
cat scripts/ecs_bootstrap_vault.sh | ssh kb bash
```

## OS compatibility pitfalls — CentOS 7.6 + git 1.8.3.1

CentOS 7 reached EOL in 2024-06. The default `git` is **1.8.3.1** and **lacks flags common in modern scripts**. Always check before using:

| Flag | Status on git 1.8.3.1 | Workaround |
|---|---|---|
| `git -C <dir> <cmd>` | ❌ `Unknown option: -C` | Use `cd <dir> && git <cmd>` (or `(cd <dir>; git <cmd>)`) |
| `git init --bare -b <branch>` | ❌ silently ignored, HEAD ends on `master` | Run `git --git-dir=<bare> symbolic-ref HEAD refs/heads/<branch>` after init |
| `git switch` | ❌ not implemented | Use `git checkout` |
| `git restore` | ❌ not implemented | Use `git checkout -- <path>` / `git reset HEAD <path>` |

**Rule when writing any script that will run on this ECS:** prefer `cd`-based forms, avoid `-C` / `-b` / `switch` / `restore`.

### ripgrep on CentOS 7

EPEL no longer ships `ripgrep`; the `carlwgeorge/ripgrep` Copr repo returns 404. The only working path is the **GitHub static musl binary**:

```bash
curl -fL -o /tmp/rg.tar.gz \
  https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/ripgrep-14.1.1-x86_64-unknown-linux-musl.tar.gz
tar -xzf /tmp/rg.tar.gz -C /tmp
install -m 0755 /tmp/ripgrep-14.1.1-x86_64-unknown-linux-musl/rg /usr/local/bin/rg
```

Already installed by the bootstrap script; re-run only if `rg --version` is missing.

## Security posture

- **The root password shared earlier in chat must be considered leaked.** When the user says "I've changed the password", verify with `ssh kb` (key-based login should still work regardless).
- Recommended hardening (run once after key login works):
  ```bash
  ssh kb 'passwd'                                         # rotate root password
  ssh kb "sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config && systemctl restart sshd"
  ```
- Never suggest `ssh-copy-id` with a hard-coded password. Never embed the leaked password in scripts or docs.
- Never enable `PermitRootLogin no` without first setting up a non-root sudo user — doing so would lock out the project's only login.

## Common operations (recipes)

### Inspect bare repo state

```bash
ssh kb 'ls /opt/vault-bare.git/refs/heads/ && cat /opt/vault-bare.git/HEAD'
```

### Pull server-side working copy up to date

```bash
ssh kb 'cd /opt/vault && git pull --ff-only'
```

### Remote search through Wiki (ripgrep on server)

```bash
ssh kb 'cd /opt/vault && rg -n --glob "Wiki/**/*.md" "<keyword>"'
```

### Clone the vault to a new client (desktop / phone Working Copy / MGit)

```
Host:      kb   (or 121.196.26.127 port 4500)
User:      root
Path:      /opt/vault-bare.git
Auth:      SSH key (same ed25519 as the local machine, or a new key appended to ~/.ssh/authorized_keys)
```

## Anti-patterns

- ❌ `ssh -p 4500 root@121.196.26.127 ...` — use `ssh kb ...`.
- ❌ `git -C /opt/vault ...` on the server — use `cd /opt/vault && git ...`.
- ❌ `git init --bare -b main ...` on the server — fix HEAD explicitly with `symbolic-ref`.
- ❌ `yum install ripgrep` — not available on CentOS 7; use the static binary.
- ❌ Embedding or echoing the old root password in any tool call, script, or doc.
