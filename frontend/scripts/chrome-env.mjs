// Chrome checks the ProgramFiles variables to tell whether it is the system-level install.
// Started from a trimmed environment without them, it takes itself for a per-user install
// and rewrites the user's pinned taskbar shortcut to the per-user AppUserModelID, which
// splits everyday Chrome off its taskbar pin. Always hand Chrome these variables.
export const chromeEnv = {
  ...process.env,
  ProgramFiles: process.env.ProgramFiles || 'C:\\Program Files',
  ProgramW6432: process.env.ProgramW6432 || 'C:\\Program Files',
  'ProgramFiles(x86)': process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)',
}
