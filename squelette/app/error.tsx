"use client";

import Link from "next/link";
import { useEffect } from "react";

/**
 * QUAND QUELQUE CHOSE CASSE.
 *
 * Sans ce fichier, une erreur affiche l'écran par défaut de Next : en anglais.
 * Il doit être un composant client, seule façon d'attraper une erreur survenue
 * pendant le rendu.
 *
 * ON N'AFFICHE PAS `error.message` : un message technique renseigne un
 * attaquant et n'aide personne d'autre. La trace part dans la console, où le
 * `digest` permet de la retrouver.
 */
export default function Erreur({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Erreur de rendu", error.digest ?? error);
  }, [error]);

  return (
    <section className="section section--tete">
      <div className="conteneur conteneur--texte">
        <p className="surtitre">Incident</p>
        <h1 className="titre-page">Quelque chose n&apos;a pas fonctionné</h1>
        <p className="chapo">
          La page n&apos;a pas pu s&apos;afficher. C&apos;est souvent passager :
          réessayer suffit la plupart du temps.
        </p>
        <p className="article__nav">
          <button className="btn btn--plein" type="button" onClick={reset}>
            Réessayer
          </button>
          <Link className="btn btn--contour" href="/">
            Retour à l&apos;accueil
          </Link>
        </p>
      </div>
    </section>
  );
}
