/**
 * LES ADRESSES DU SITE : ce que le plan du site et le flux ont besoin de savoir.
 *
 * Livré avec la seule page d'accueil. LE CREW AJOUTE UNE ENTRÉE PAR COLLECTION
 * qu'il engendre, en lisant ses propres fonctions de `lib/data/`.
 *
 * Pourquoi cette fonction existe plutôt qu'une liste écrite dans sitemap.ts :
 * une liste à tenir à jour à la main finit toujours par oublier les dernières
 * pages, et les moteurs de recherche ne les voient jamais.
 */
export type AdresseDuSite = {
  /** Le chemin, à partir de la racine : « / », « /blog/mon-billet ». */
  chemin: string;
  /** Date ISO de dernière modification, ou null si on ne la connaît pas. */
  modifiee: string | null;
  /** Titre et résumé : utilisés par le flux, ignorés par le plan du site. */
  titre?: string;
  resume?: string;
};

export async function adressesDuSite(): Promise<AdresseDuSite[]> {
  return [{ chemin: "/", modifiee: null, titre: "Accueil" }];
}
