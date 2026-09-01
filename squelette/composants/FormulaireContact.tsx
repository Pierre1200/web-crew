"use client";

import { useEffect, useRef, useState } from "react";
import { SITE } from "@/site.config";
import {
  envoyerMessage,
  type NouveauMessage,
  type ResultatEnvoi,
} from "@/lib/data/messages";

/**
 * LE FORMULAIRE DE CONTACT.
 *
 * Il assemble un `NouveauMessage` et le confie à `envoyerMessage`. Il ne sait
 * rien de ce qu'il y a derrière : un service tiers aujourd'hui, une table
 * demain. C'est la couture, du côté écriture.
 *
 * ON N'UTILISE PAS `<form action={…}>`. React 19 remet alors les champs à zéro
 * après chaque envoi, y compris quand l'envoi est REFUSÉ : la personne lit
 * « cette adresse ne semble pas complète » sous un formulaire redevenu vide.
 * Avec `onSubmit` et `preventDefault`, le navigateur garde la saisie telle
 * quelle, et il n'y a rien à réafficher à la main.
 */
export function FormulaireContact() {
  const [resultat, setResultat] = useState<ResultatEnvoi | null>(null);
  const [enCours, setEnCours] = useState(false);
  const horodatage = useRef<HTMLInputElement>(null);

  // L'heure d'ouverture de la page : elle sert à repérer les envois
  // instantanés, qui ne viennent pas d'un humain.
  useEffect(() => {
    if (horodatage.current) horodatage.current.value = String(Date.now());
  }, []);

  const erreurs = resultat?.etat === "refuse" ? resultat.erreurs : {};
  const classe = (champ: string) =>
    erreurs[champ] ? "champ champ--erreur" : "champ";

  async function traiter(evenement: React.FormEvent<HTMLFormElement>) {
    evenement.preventDefault();
    const donnees = new FormData(evenement.currentTarget);
    const lire = (champ: string) => String(donnees.get(champ) ?? "").trim();

    // LES DEUX BARRIÈRES ANTI-ROBOT vivent ici et non dans la couture : elles
    // parlent du formulaire, pas de la donnée. Dans les deux cas on répond
    // « envoyé » sans rien faire, parce qu'un robot à qui l'on dit « refusé »
    // recommence en changeant de tactique.
    const piege = lire("site_web");
    const chargeA = Number(lire("charge_a"));
    const instantane = chargeA > 0 && Date.now() - chargeA < 3000;
    if (piege || instantane) {
      setResultat({ etat: "envoye" });
      return;
    }

    const message: NouveauMessage = {
      motif: lire("motif"),
      nom: lire("nom"),
      courriel: lire("courriel"),
      message: lire("message"),
    };

    setEnCours(true);
    setResultat(await envoyerMessage(message));
    setEnCours(false);
  }

  if (resultat?.etat === "envoye") {
    return (
      <p className="reponse" data-etat="ok">
        Merci, votre message est parti. Nous vous répondons dès que possible.
      </p>
    );
  }

  return (
    <form className="formulaire" onSubmit={traiter}>
      {resultat?.etat === "echec" && (
        // On n'affiche JAMAIS une fausse confirmation : en cas d'échec, la
        // personne doit repartir avec un moyen de nous joindre.
        <p className="reponse" data-etat="erreur">
          Nous n&apos;avons pas pu envoyer votre message. Écrivez-nous
          directement à <a href={`mailto:${SITE.courriel}`}>{SITE.courriel}</a>.
        </p>
      )}

      {/* Le motif n'apparaît que si le brief en a défini. Un menu déroulant à
          une seule entrée est une question posée pour rien. */}
      {SITE.formulaire.motifs.length > 0 && (
        <div className={classe("motif")}>
          <label htmlFor="motif">Votre demande</label>
          <select id="motif" name="motif" required defaultValue="">
            <option value="">Choisissez un motif…</option>
            {SITE.formulaire.motifs.map((motif) => (
              <option key={motif.valeur} value={motif.valeur}>
                {motif.libelle}
              </option>
            ))}
          </select>
          {erreurs.motif && <p className="champ__erreur">{erreurs.motif}</p>}
        </div>
      )}

      <div className={classe("nom")}>
        <label htmlFor="nom">Votre nom</label>
        <input type="text" id="nom" name="nom" autoComplete="name" required />
        {erreurs.nom && <p className="champ__erreur">{erreurs.nom}</p>}
      </div>

      <div className={classe("courriel")}>
        <label htmlFor="courriel">Votre adresse électronique</label>
        <input type="email" id="courriel" name="courriel" autoComplete="email" required />
        <p className="champ__aide">Pour que nous puissions vous répondre.</p>
        {erreurs.courriel && <p className="champ__erreur">{erreurs.courriel}</p>}
      </div>

      <div className={`${classe("message")} champ--message`}>
        <label htmlFor="message">Votre message</label>
        <textarea id="message" name="message" required />
        {erreurs.message && <p className="champ__erreur">{erreurs.message}</p>}
      </div>

      {/* LE CHAMP-PIÈGE. Sorti de l'écran plutôt que masqué par display:none,
          que certains robots savent détecter. aria-hidden et tabIndex=-1 pour
          qu'un lecteur d'écran ne l'annonce jamais : un piège qui piégerait un
          utilisateur aveugle serait pire que pas de piège du tout. */}
      <div className="piege" aria-hidden="true">
        <label htmlFor="site_web">Ne remplissez pas ce champ</label>
        <input type="text" id="site_web" name="site_web" tabIndex={-1} autoComplete="off" />
      </div>
      <input type="hidden" name="charge_a" ref={horodatage} />

      <div className="formulaire__pied">
        <button className="btn btn--plein" type="submit" disabled={enCours}>
          {enCours ? "Envoi en cours…" : "Envoyer le message"}
        </button>
        <p className="formulaire__direct">
          Ou écrire directement à{" "}
          <a href={`mailto:${SITE.courriel}`}>{SITE.courriel}</a>.
        </p>
      </div>
    </form>
  );
}
