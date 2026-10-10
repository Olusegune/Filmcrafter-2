// the layout tests read style files from disk (a css import is empty under the test runner); only these calls are needed
declare module "node:fs" { export function readFileSync(path: string, encoding: "utf8"): string; export function existsSync(path: string): boolean; }
