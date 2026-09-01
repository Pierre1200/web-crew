/**
 * L'ADRESSE PUBLIQUE DU SITE, écrite à un seul endroit.
 *
 * Trois choses en ont besoin en entier, là où le reste du site se contente de
 * chemins relatifs : le plan du site, le robots.txt, et les aperçus de lien.
 *
 * ⚠️ EN EXPORT STATIQUE, CETTE VALEUR EST LUE À LA CONSTRUCTION. Elle doit
 * donc être posée dans l'environnement AVANT de lancer le build, pas au
 * déploiement.
 */
export const ADRESSE_DU_SITE =
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://exemple.fr";
