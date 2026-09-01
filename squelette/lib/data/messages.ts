import { SITE } from "@/site.config";

/**
 * L'ÉCRITURE D'UN MESSAGE : le côté écriture de la couture.
 *
 * `lib/data/` n'est pas seulement la lecture. Un formulaire demandé dans le
 * brief est une TABLE de la future base, pas un envoi de courriel déguisé. Il
 * suit donc les mêmes règles que le reste : une fonction nommée, une charge
 * utile typée, et un corps qu'on remplace sans que le formulaire s'en aperçoive.
 *
 * AUJOURD'HUI : poste vers le service configuré dans site.config.ts.
 *
 *   const reponse = await fetch(SITE.formulaire.adresseEnvoi, { ... });
 *   return reponse.ok ? { etat: "envoye" } : { etat: "echec" };
 *
 * DEMAIN, avec une base : même nom, même charge utile, même type de retour.
 *
 *   const { error } = await supabase.from("messages").insert(message);
 *   return error ? { etat: "echec" } : { etat: "envoye" };
 *
 * L'insertion se fait depuis le navigateur, avec la clé publiable, et c'est une
 * règle RLS « chacun peut déposer un message » qui l'autorise. Un site statique
 * n'a donc pas besoin de serveur pour écrire en base. Cette règle et la table
 * s'écrivent à la main : le crew ne produit ni schéma ni RLS.
 */

/**
 * LA FORME D'UN MESSAGE, telle qu'elle existera en base.
 *
 * Les noms sont ceux des futures colonnes, en minuscules avec des tirets bas :
 * une divergence ici est un renommage à faire partout plus tard.
 *
 * Ce qui n'est PAS ici est aussi important : pas d'`id` (la base le fabrique),
 * pas de `cree_le` (elle l'horodate), pas de `lu` (c'est l'affaire du
 * back-office, qui n'existe pas encore). On n'envoie que des faits saisis par
 * la personne.
 */
export type NouveauMessage = {
  /** Une valeur de SITE.formulaire.motifs, qui deviendra une contrainte
   *  `check` de la table. Les deux listes doivent dire la même chose. */
  motif: string;
  nom: string;
  courriel: string;
  message: string;
};

export type ResultatEnvoi =
  | { etat: "envoye" }
  | { etat: "refuse"; erreurs: Record<string, string> }
  | { etat: "echec" };

/**
 * Les vérifications faites avant l'envoi.
 *
 * Elles recopient les contraintes que portera la table : longueur maximale,
 * champs obligatoires, liste fermée des motifs. Ici elles servent à afficher un
 * message compréhensible, là-bas elles seront la vraie barrière. Une
 * vérification côté navigateur seule ne protège rien.
 */
function verifier(message: NouveauMessage): Record<string, string> {
  const erreurs: Record<string, string> = {};

  if (SITE.formulaire.motifs.length > 0 && !SITE.formulaire.motifs.some((m) => m.valeur === message.motif)) {
    erreurs.motif = "Choisissez le motif de votre message.";
  }
  if (!message.nom) {
    erreurs.nom = "Indiquez votre nom, pour que nous sachions qui écrit.";
  }
  // Volontairement permissif : la seule vérification qui vaille, c'est qu'un
  // courriel arrive. Un contrôle strict rejette surtout des adresses valides
  // mais inhabituelles.
  if (!message.courriel.includes("@") || message.courriel.length < 5) {
    erreurs.courriel = "Cette adresse ne semble pas complète.";
  }
  if (!message.message) erreurs.message = "Votre message est vide.";
  if (message.message.length > 5000) erreurs.message = "Votre message est trop long.";

  return erreurs;
}

export async function envoyerMessage(
  message: NouveauMessage,
): Promise<ResultatEnvoi> {
  const erreurs = verifier(message);
  if (Object.keys(erreurs).length > 0) return { etat: "refuse", erreurs };

  const adresse = SITE.formulaire.adresseEnvoi;
  // Pas de destination configurée : on ne fait JAMAIS semblant d'avoir envoyé.
  // Le formulaire affiche alors le courriel direct.
  if (!adresse) return { etat: "echec" };

  try {
    const reponse = await fetch(adresse, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(message),
    });
    return reponse.ok ? { etat: "envoye" } : { etat: "echec" };
  } catch {
    return { etat: "echec" };
  }
}
