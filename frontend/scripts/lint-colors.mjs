import { readdir, readFile } from 'node:fs/promises'
import { dirname, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const builtins = 'amber|yellow|teal|emerald|green|rose|red|sky|blue|violet|purple|fuchsia|pink|lime|slate|gray|zinc|neutral|stone|orange|cyan|indigo'
const hex = /(?<![\w-])#(?:[\da-f]{8}|[\da-f]{6}|[\da-f]{3})(?![\w-])/gi
const functions = /\b(?:rgba?|hsla?)\(\s*(?!\s|var\(|from\s)/gi
const classes = new RegExp(`(?<![\\w-])(?:[a-z]+-)+(?:${builtins})-\\d{2,3}(?![\\w-])`, 'g')

export async function scanColors() {
  const findings = []
  async function visit(dir) {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const path = resolve(dir, entry.name)
      const name = relative(frontend, path).replaceAll('\\', '/')
      if (name === 'src/assets' || name === 'src/styles/tokens.css') continue
      if (entry.isDirectory()) await visit(path)
      else if (/\.(vue|css|js)$/.test(name)) {
        const source = await readFile(path, 'utf8')
        const count = [...source.matchAll(hex), ...source.matchAll(functions), ...source.matchAll(classes)].length
        if (count) findings.push({ path: name, count })
      }
    }
  }
  await visit(resolve(frontend, 'src'))
  return findings.sort((a, b) => a.path.localeCompare(b.path))
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const allow = JSON.parse(await readFile(resolve(frontend, 'scripts/lint-colors.allow.json'), 'utf8'))
    if (!Array.isArray(allow) || allow.some(path => typeof path !== 'string')) throw new Error('Color allowlist must be an array of relative paths')
    const allowed = new Set(allow.map(path => path.replaceAll('\\', '/')))
    const findings = await scanColors()
    for (const item of findings) console.log(`${item.path}: ${item.count} violations (${allowed.has(item.path) ? 'allowlisted' : 'NEW'})`)
    const failures = findings.filter(item => !allowed.has(item.path))
    console.log(`Color lint: ${findings.reduce((sum, item) => sum + item.count, 0)} violations in ${findings.length} files; ${findings.length - failures.length} allowlisted; ${failures.length} unallowlisted.`)
    process.exitCode = failures.length ? 1 : 0
  } catch (error) {
    console.error(error.message)
    process.exitCode = 1
  }
}
