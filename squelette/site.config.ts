/**
 * LA CONFIGURATION DU SITE : le seul fichier à remplir pour un nouveau client.
 *
 * Tout ce qui change d'un client à l'autre et qui n'est pas du contenu vit ici.
 * Aucun composant n'écrit en dur un nom, une adresse ou un courriel : ils lisent
 * cet objet. Une information n'existe donc qu'à un seul endroit.
 *
 * Les clés de `mentions` reprennent celles produites par `utils/mentions.py`,
 * pour que le passage du config.json Python à ce fichier soit une recopie.
 */

/** Une collection de contenus : les expositions, le blog, les réalisations… */
export type Collection = {
  /** Le nom du dossier dans `contenu/`, et la racine des adresses. */
  identifiant: string;
  titre: string;
  /** Un flux RSS est-il publié pour cette collection ? */
  flux: boolean;
};

export const SITE = {
  nom: "Nom du site",
  accroche: "La phrase qui dit ce qu'est le lieu.",
  description:
    "Une à deux phrases. Elles servent au référencement et à l'aperçu " +
    "affiché quand on colle le lien dans un message.",

  courriel: "contact@exemple.fr",
  telephone: "",

  /** L'ordre du menu principal, tel qu'il s'affiche. */
  menu: [
    { href: "/", libelle: "Accueil" },
  ] as { href: string; libelle: string }[],

  /**
   * L'image d'aperçu des liens partagés. Ses dimensions doivent être exactes :
   * un aperçu déclaré au mauvais format est recadré de travers.
   */
  partage: {
    chemin: "/assets/partage.webp",
    largeur: 1200,
    hauteur: 630,
    alt: "",
  },

  /** Les collections engendrées par le crew. Vide tant qu'il n'y en a pas. */
  collections: [] as Collection[],

  /**
   * LE FORMULAIRE DE CONTACT, s'il est demandé dans le brief.
   *
   * Il est pensé comme une TABLE de la future base, pas comme un envoi de
   * courriel. Voir lib/data/messages.ts : le jour du branchement, seul le
   * corps de la fonction change.
   *
   * `motifs` deviendra une contrainte `check` de la table. Une liste courte et
   * fermée, décidée depuis le brief : elle sert à trier les messages, pas à
   * interroger la personne qui écrit.
   *
   * `adresseEnvoi` est la destination provisoire, tant qu'il n'y a pas de base.
   * `null` désactive le formulaire et ne laisse que le lien de courriel : un
   * état acceptable pour une mise en ligne, contrairement à un formulaire qui
   * ferait semblant d'envoyer.
   */
  formulaire: {
    motifs: [] as { valeur: string; libelle: string }[],
    adresseEnvoi: null as string | null,
  },

  /**
   * LES MENTIONS LÉGALES. Obligatoires (LCEN, article 6 III).
   * Ce qui reste vide s'affiche « à compléter » EN ÉVIDENCE sur la page :
   * un trou qu'on voit est un trou qu'on finit par boucher.
   */
  mentions: {
    editeur: "",
    statut: "",
    adresse: "",
    siret: "",
    rna: "",
    directeur: "",
    email: "",
    telephone: "",
    hebergeur: { nom: "", adresse: "", site: "" },
  },
};
