/**
 * TOUT CE QUI TOUCHE AUX DATES, regroupé pour que deux pages ne puissent pas
 * écrire la même date de deux façons.
 */

/** En français le premier du mois s'écrit « 1ᵉʳ ». `Intl` ne le sait pas. */
function ordinal(jour: number): string {
  return jour === 1 ? "1ᵉʳ" : String(jour);
}

/** « 2026-08-02 » donne « 2 août 2026 ». */
export function enFrancais(date: string): string {
  // Midi UTC plutôt que minuit : à minuit, un décalage horaire fait reculer
  // la date d'un jour.
  const d = new Date(`${date}T12:00:00Z`);
  const moisEtAnnee = d.toLocaleDateString("fr-FR", {
    month: "long",
    year: "numeric",
    timeZone: "Europe/Paris",
  });
  return `${ordinal(d.getUTCDate())} ${moisEtAnnee}`;
}

/** « 2 – 30 août 2026 », sans répéter le mois ni l'année quand c'est inutile. */
export function periode(debut: string, fin: string): string {
  const d = new Date(`${debut}T12:00:00Z`);
  const f = new Date(`${fin}T12:00:00Z`);

  const memeAnnee = d.getUTCFullYear() === f.getUTCFullYear();
  const memeMois = memeAnnee && d.getUTCMonth() === f.getUTCMonth();

  if (memeMois) return `${ordinal(d.getUTCDate())} – ${enFrancais(fin)}`;

  if (memeAnnee) {
    const mois = d.toLocaleDateString("fr-FR", {
      month: "long",
      timeZone: "Europe/Paris",
    });
    return `${ordinal(d.getUTCDate())} ${mois} – ${enFrancais(fin)}`;
  }

  return `${enFrancais(debut)} – ${enFrancais(fin)}`;
}

export type Etat = {
  libelle: string;
  classe: "en-cours" | "a-venir" | "passee";
} | null;

/**
 * L'état déduit de deux dates. CALCULÉ, JAMAIS STOCKÉ : « en cours » écrit
 * dans une donnée devient un mensonge le lendemain de la fermeture.
 *
 * ⚠️ À N'APPELER QUE DEPUIS UN COMPOSANT CLIENT (voir composants/Etat.tsx).
 * Appelé pendant le rendu d'une page, il serait figé au jour du build : le
 * site afficherait « En cours » des mois après. Rien ne le signalerait, ni le
 * compilateur, ni la capture visuelle faite le jour même.
 */
export function etat(debut: string, fin: string): Etat {
  // On compare des JOURS et non des instants : une exposition qui ferme
  // « le 30 » est ouverte pendant tout le 30. « sv-SE » donne AAAA-MM-JJ,
  // directement comparable à nos dates.
  const aujourdhui = new Date().toLocaleDateString("sv-SE", {
    timeZone: "Europe/Paris",
  });

  const joursEntre = (de: string, a: string) =>
    Math.round((Date.parse(`${a}T12:00:00Z`) - Date.parse(`${de}T12:00:00Z`)) / 86400000);

  if (aujourdhui < debut) {
    const jours = joursEntre(aujourdhui, debut);
    // « Bientôt » ne veut rien dire à six mois : au-delà de deux mois, on
    // laisse les dates parler toutes seules.
    if (jours > 62) return null;
    return { libelle: jours <= 1 ? "Ouvre demain" : "Bientôt", classe: "a-venir" };
  }

  if (aujourdhui > fin) return { libelle: "Terminé", classe: "passee" };

  const restants = joursEntre(aujourdhui, fin);
  return {
    libelle:
      restants === 0
        ? "Dernier jour"
        : restants <= 7
          ? `En cours, plus que ${restants} jour${restants > 1 ? "s" : ""}`
          : "En cours",
    classe: "en-cours",
  };
}
