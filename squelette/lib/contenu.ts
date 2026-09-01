import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

/**
 * LA LECTURE DES FICHIERS DE CONTENU.
 *
 * Le contenu vit dans `contenu/<collection>/*.json`, un fichier par entrée.
 * Ce module ne fait que lire et analyser : il ne trie pas, ne filtre pas, ne
 * connaît aucun type métier. Le tri et le filtrage sont le travail de
 * `lib/data/`, qui est la couture avec la future base.
 *
 * ⚠️ NE JAMAIS L'IMPORTER DEPUIS UN COMPOSANT CLIENT : il lit le disque, ce
 * qu'un navigateur ne sait pas faire. Il ne s'exécute qu'à la construction.
 *
 * POURQUOI `async` ALORS QU'ON LIT UN FICHIER LOCAL. C'est la règle la plus
 * importante et la moins évidente du projet. Une fonction synchrone rend
 * synchrones tous ses appelants ; la rendre asynchrone plus tard oblige à
 * toucher chaque composant. Aujourd'hui, ça ne coûte rien.
 */

const RACINE = path.join(process.cwd(), "contenu");

/** Toutes les entrées d'une collection, dans l'ordre des noms de fichiers. */
export async function lireCollection<T>(identifiant: string): Promise<T[]> {
  const dossier = path.join(RACINE, identifiant);

  let fichiers: string[];
  try {
    fichiers = (await readdir(dossier)).filter((f) => f.endsWith(".json")).sort();
  } catch {
    // Une collection déclarée mais pas encore remplie n'est pas une erreur :
    // le site doit construire, avec une liste vide.
    return [];
  }

  return Promise.all(
    fichiers.map(async (fichier) => {
      const brut = await readFile(path.join(dossier, fichier), "utf8");
      return JSON.parse(brut) as T;
    }),
  );
}

/** Un fichier isolé, par exemple `contenu/accueil.json`. */
export async function lireFichier<T>(nom: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path.join(RACINE, nom), "utf8")) as T;
  } catch {
    return null;
  }
}
