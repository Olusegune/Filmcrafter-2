/** Where things live on disk, for both kinds of path separator (Windows uses a backslash, macOS and Linux a slash). */

/** The film's folder when given its render project's folder (a film keeps its render project inside it), otherwise the same path. */
export function filmDirOfRender(dir: string): string {
  return String(dir).replace(/[\\/]+$/, "").replace(/[\\/]render$/i, "");
}

/** The film's folder when given its double-clickable `.filmcrafter` document, otherwise the same path. */
export function filmDirOfDoc(path: string): string {
  return String(path).replace(/[\\/][^\\/]+\.filmcrafter$/i, "");
}

/** Is this the folder of a film's render project? */
export const isRenderDir = (dir: string): boolean => /[\\/]render[\\/]*$/i.test(String(dir));

/** A Producer package (a PULSEFRAME music-video planning package): FilmCrafter does not import these. */
export const isProducerPackage = (p: string) => /\.(pfproducer|zip)$|[\\/]manifest\.json$/i.test(p);
