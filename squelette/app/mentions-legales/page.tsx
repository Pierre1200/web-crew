import type { Metadata } from "next";
import { SITE } from "@/site.config";

/**
 * LES MENTIONS LÉGALES. Obligatoires pour tout site édité en France
 * (loi pour la confiance dans l'économie numérique, article 6 III).
 *
 * CE QUI MANQUE EST AFFICHÉ EN ÉVIDENCE, pas laissé en commentaire dans le
 * code : un encadré qu'on voit est un encadré qu'on finit par remplir. La même
 * liste est calculée côté Python par `utils/mentions.champs_manquants()`.
 */
export const metadata: Metadata = {
  title: `Mentions légales · ${SITE.nom}`,
  // Une page d'obligation légale n'a rien à faire dans les résultats de
  // recherche : elle capterait des visites qui cherchaient autre chose.
  robots: { index: false, follow: true },
};

/** Les informations légalement attendues qui n'ont pas été renseignées. */
function champsManquants(): string[] {
  const m = SITE.mentions;
  const manquants: string[] = [];

  if (!m.editeur) manquants.push("le nom de l'éditeur du site");
  if (!m.directeur) manquants.push("le directeur de la publication");
  if (!m.hebergeur.nom) manquants.push("le nom de l'hébergeur");
  if (!m.hebergeur.adresse) manquants.push("l'adresse de l'hébergeur");
  if (!m.siret && !m.rna) manquants.push("le SIRET ou le numéro RNA");

  return manquants;
}

/** Une ligne du tableau, ou rien du tout si la valeur est vide. */
function Ligne({ intitule, valeur }: { intitule: string; valeur: string }) {
  if (!valeur) return null;
  return (
    <>
      <dt>{intitule}</dt>
      <dd>{valeur}</dd>
    </>
  );
}

export default function MentionsLegales() {
  const manquants = champsManquants();
  const m = SITE.mentions;

  return (
    <section className="section mentions">
      <div className="conteneur conteneur--texte">
        <h1>Mentions légales</h1>

        {manquants.length > 0 && (
          <p className="mentions__alerte">
            <strong>À compléter avant la mise en ligne.</strong> Ces
            informations sont obligatoires et ne peuvent pas être devinées
            depuis le code&nbsp;: {manquants.join(", ")}.
          </p>
        )}

        <h2>L&apos;éditeur du site</h2>
        <dl>
          <Ligne intitule="Dénomination" valeur={m.editeur} />
          <Ligne intitule="Forme juridique" valeur={m.statut} />
          <Ligne intitule="Siège social" valeur={m.adresse} />
          <Ligne intitule="SIRET" valeur={m.siret} />
          <Ligne intitule="Numéro RNA" valeur={m.rna} />
          <Ligne intitule="Directeur de la publication" valeur={m.directeur} />
          <Ligne intitule="Courriel" valeur={m.email || SITE.courriel} />
          <Ligne intitule="Téléphone" valeur={m.telephone} />
        </dl>

        <h2>Hébergement</h2>
        {/* Une liste de définitions vide sous un titre ressemble à un bug.
            Tant que rien n'est renseigné, on l'écrit en toutes lettres. */}
        {m.hebergeur.nom ? (
          <dl>
            <Ligne intitule="Hébergeur" valeur={m.hebergeur.nom} />
            <Ligne intitule="Adresse" valeur={m.hebergeur.adresse} />
            <Ligne intitule="Site" valeur={m.hebergeur.site} />
          </dl>
        ) : (
          <p>
            <strong>À renseigner&nbsp;:</strong> raison sociale, adresse postale
            et numéro de téléphone de l&apos;hébergeur, conformément à
            l&apos;article 6 III de la loi pour la confiance dans
            l&apos;économie numérique.
          </p>
        )}

        <h2>Données personnelles</h2>
        <p>
          Ce site ne dépose aucun cookie et ne recourt à aucune mesure
          d&apos;audience. Les polices de caractères sont servies depuis ce
          domaine et non depuis un tiers&nbsp;: aucune donnée de navigation
          n&apos;est transmise en dehors du site.
        </p>
        <p>
          Conformément au règlement général sur la protection des données, vous
          pouvez demander l&apos;accès, la rectification ou l&apos;effacement
          des informations vous concernant en écrivant à{" "}
          <a href={`mailto:${SITE.courriel}`}>{SITE.courriel}</a>.
        </p>
      </div>
    </section>
  );
}
