import { spawn } from 'node:child_process'

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe'

// Chrome checks the ProgramFiles variables to tell whether it is the system-level install.
// Started from a trimmed environment without them, it takes itself for a per-user install
// and rewrites the user's pinned taskbar shortcut to the per-user AppUserModelID, which
// splits everyday Chrome off its taskbar pin. Always hand Chrome these variables, rooted
// where this Chrome actually lives.
function programFilesFor(chromePath) {
  const root = chromePath.match(/^(.+?[\\/]Program Files)(?: \(x86\))?[\\/]/i)?.[1]
  return root ? root.replace(/\//g, '\\') : `${process.env.SystemDrive || 'C:'}\\Program Files`
}

export function chromeEnv(chromePath) {
  const programFiles = programFilesFor(chromePath)
  return {
    ...process.env,
    ProgramFiles: process.env.ProgramFiles || programFiles,
    ProgramW6432: process.env.ProgramW6432 || programFiles,
    'ProgramFiles(x86)': process.env['ProgramFiles(x86)'] || `${programFiles} (x86)`,
  }
}

// Headless Chrome for the smoke scripts: CDP on `port`, or on fds 3/4 with `pipe`.
export function launchChrome({ profile, port, pipe = false, flags = [], stdio = pipe ? ['ignore', 'ignore', 'ignore', 'pipe', 'pipe'] : 'ignore' }) {
  if (!profile) throw new Error('launchChrome needs a profile directory')
  if (!pipe && port == null) throw new Error('launchChrome needs a CDP port, or pipe: true')
  const chromePath = process.env.CHROME_PATH || CHROME_PATH
  const debugging = pipe ? ['--remote-debugging-pipe'] : [`--remote-debugging-port=${port}`, '--remote-allow-origins=*']
  return spawn(chromePath, [
    '--headless=new', ...flags, '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    ...debugging, `--user-data-dir=${profile}`, 'about:blank',
  ], { env: chromeEnv(chromePath), windowsHide: true, stdio })
}
