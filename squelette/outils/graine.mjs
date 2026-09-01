/**
 * DU CONTENU LOCAL VERS DES INSERT SQL.
 *
 *   node outils/graine.mjs expositions > graine.sql
 *
 * C'est la continuité entre les deux étapes du produit : le fichier de contenu
 * produit par le crew sert de semence à la future base, sans ressaisie. Le jour
 * où un client veut son back-office, sa saison est déjà en ligne.
 *
 * Le script ne connaît aucun schéma : il déduit les colonnes des clés du JSON.
 * Ce qui suppose que toutes les entrées d'une collection ont la même forme,
 * ce qui est déjà la règle du modèle de contenu.
 */
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

const collection = process.argv[2];
if (!collection) {
  console.error("Usage : node outils/graine.mjs <collection>");
  process.exit(1);
}

const dossier = path.join(process.cwd(), "contenu", collection);
const fichiers = (await readdir(dossier)).filter((f) => f.endsWith(".json")).sort();

/** Une valeur JSON dans sa forme SQL. Les apostrophes se doublent. */
function litteral(valeur) {
  if (valeur === null || valeur === undefined) return "null";
  if (typeof valeur === "boolean") return valeur ? "true" : "false";
  if (typeof valeur === "number") return String(valeur);
  // Un tableau ou un objet part en JSONB plutôt qu'en texte illisible.
  if (typeof valeur === "object") {
    return `'${JSON.stringify(valeur).replaceAll("'", "''")}'::jsonb`;
  }
  return `'${String(valeur).replaceAll("'", "''")}'`;
}

const entrees = await Promise.all(
  fichiers.map(async (f) => JSON.parse(await readFile(path.join(dossier, f), "utf8"))),
);

if (entrees.length === 0) {
  console.error(`Aucune entrée dans contenu/${collection}/`);
  process.exit(1);
}

// `id` est laissé à la base : elle sait fabriquer un UUID, et un identifiant
// inventé ici entrerait en collision avec ceux qui suivront.
const colonnes = Object.keys(entrees[0]).filter((c) => c !== "id");

console.log(`-- Engendré depuis contenu/${collection}/ le ${new Date().toISOString()}`);
console.log(`insert into ${collection} (${colonnes.join(", ")}) values`);
console.log(
  entrees
    .map((entree) => `  (${colonnes.map((c) => litteral(entree[c] ?? null)).join(", ")})`)
    .join(",\n"),
);
// Rejouer la graine ne doit rien casser : le slug est unique, on ignore les
// doublons plutôt que d'échouer au milieu du lot.
console.log("on conflict (slug) do nothing;");
