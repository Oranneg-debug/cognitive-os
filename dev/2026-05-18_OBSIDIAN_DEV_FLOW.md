# [[2026-05-18]] Proposal: Obsidian Plugin Development Architecture

**Date**: 2026-05-18  
**Author**: Cline (AI Assistant)  
**Status**: Under Review  

---

## 🔍 Problem Statement

### Current Situation
- **Vault Location**: `E:\Oranneg\CloudStation\Documents\Obsidian\Grand Nexus`
- **Source Code**: `E:\Antigravity\obsidian-lmstudio-agent`

The user manually copies built plugin files (`main.js`, `manifest.json`, `styles.css`) from the source directory to Obsidian's plugin folder to test changes.

### Pain Points
1. Manual copy-paste workflow after each build
2. Time-consuming iteration cycle for development
3. Risk of forgetting to copy files

---

## 💡 Proposed Solution(s)

### Option 1: Symlink Approach (Recommended)
Create symbolic links from the vault's plugin directory pointing to the source build output.

**Structure:**
```
Vault\.obsidian\plugins\lmstudio-agent\
├── main.js      -> E:\Antigravity\...\main.js (symlink)
├── manifest.json -> E:\Antigravity\...\manifest.json (symlink)
└── styles.css   -> E:\Antigravity\...\styles.css (symlink)
```

**Setup Script (`setup-dev.bat`):**
```batch
@echo off
cd /d "%~dp0"
set VAULT=E:\Oranneg\CloudStation\Documents\Obsidian\Grand Nexus
set PLUGIN_DIR=%VAULT%\.obsidian\plugins\lmstudio-agent

if not exist "%PLUGIN_DIR%" mkdir "%PLUGIN_DIR%"

mklink /H "%PLUGIN_DIR%\main.js" "E:\Antigravity\obsidian-lmstudio-agent\main.js"
mklink /H "%PLUGIN_DIR%\manifest.json" "E:\Antigravity\obsidian-lmstudio-agent\manifest.json"
mklink /H "%PLUGIN_DIR%\styles.css" "E:\Antigravity\obsidian-lmstudio-agent\styles.css"

echo Development setup complete!
```

**Pros:**
- Zero manual copying required
- Changes reflect instantly in Obsidian (just refresh)
- Works with `npm run dev` watch mode
- Clean separation of source vs. deployment

**Cons:**
- Requires running setup once (with admin privileges on Windows)
- Symlinks may break if paths change
- Some antivirus software may flag symlinks

---

### Option 2: Post-Build Copy Script (Simplest)

Automate the copy-paste with an npm script that runs after build.

**Structure:**
```
E:\Antigravity/
├── obsidian-lmstudio-agent/
│   ├── scripts/
│   │   └── deploy.js (copy files to vault)
│   └── package.json (with deploy script)
```

**Deploy Script (`scripts/deploy.js`):**
```javascript
import fs from 'fs';
import path from 'path';

const VAULT_PATH = 'E:\\Oranneg\\CloudStation\\Documents\\Obsidian\\Grand Nexus';
const SOURCE_DIR = path.dirname(import.meta.url.slice(7));
const PLUGIN_TARGET = path.join(VAULT_PATH, '.obsidian', 'plugins', 'lmstudio-agent');

// Create target directory if it doesn't exist
if (!fs.existsSync(PLUGIN_TARGET)) {
  fs.mkdirSync(PLUGIN_TARGET, { recursive: true });
}

// Copy files
const filesToCopy = ['main.js', 'manifest.json', 'styles.css'];
filesToCopy.forEach(file => {
  const src = path.join(SOURCE_DIR, file);
  const dst = path.join(PLUGIN_TARGET, file);
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, dst);
    console.log(`Copied ${file}`);
  }
});

console.log('Deployment complete!');
```

**package.json Update:**
```json
{
  "scripts": {
    "build": "... && node scripts/deploy.js",
    "deploy": "node scripts/deploy.js"
  }
}
```

**Pros:**
- Works without admin privileges
- Version-controlled deployment logic
- Can be run manually or as part of build process

**Cons:**
- Still involves copying (slower than symlinks)
- Multiple file operations on each deploy

---

### Option 3: Git Submodule Approach

Add the vault as a git submodule, then use npm scripts to auto-deploy.

**Structure:**
```
E:\Antigravity/
├── .gitmodules
├── obsidian-lmstudio-agent/
│   └── package.json (scripts with deploy target)
└── obsidian-vault/ (submodule)
    └── .obsidian\plugins\lmstudio-agent\ -> copy files here
```

**Pros:**
- Version-controlled relationship
- Can use git workflows

**Cons:**
- More complex setup
- Submodule management overhead
- May not work if vault isn't a git repo

---

## 🏗️ Implementation Plan

### If choosing Option 1 (Symlinks):

| Step | Action |
|------|--------|
| 1 | Create `setup-dev.bat` script in `obsidian-lmstudio-agent/` |
| 2 | Run script with admin privileges once to create symlinks |
| 3 | Update README.md with development setup instructions |
| 4 | Add `.vscode/settings.json` for recommended VS Code tasks |

### If choosing Option 2 (Copy Script):

| Step | Action |
|------|--------|
| 1 | Create `scripts/` directory in `obsidian-lmstudio-agent/` |
| 2 | Create `deploy.js` script with deployment logic |
| 3 | Update `package.json` to add `deploy` script |
| 4 | Test by running `npm run deploy` |

---

## 📋 Checklist

- [x] Documented all options considered
- [x] Pros/Cons analyzed for each option
- [x] Implementation plan is clear and actionable
- [ ] Awaiting user decision on which approach to implement

---

## 🔗 References & Backlinks

- [../obsidian-lmstudio-agent/package.json](../obsidian-lmstudio-agent/package.json) - Current build configuration
- [../docs/DEV_FOLDERS.md](../docs/DEV_FOLDERS.md) - Dev folder structure (if created)

---

## 📊 Decision Log

| Date | Decision | Notes |
|------|----------|-------|
| 2026-05-18 | Under Review | Awaiting user input on preferred approach |

---

*Proposal stored at: dev/2026-05-18_OBSIDIAN_DEV_FLOW.md*