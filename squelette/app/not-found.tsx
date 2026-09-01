import Link from "next/link";
import { Trait } from "@/composants/Trait";

/**
 * LA PAGE 404.
 *
 * Elle hérite de l'enveloppe posée dans le layout racine : le visiteur perdu
 * garde donc son menu, ce qui est le seul moment où il en a vraiment besoin.
 *
 * ELLE NE PLAISANTE PAS. Une page d'erreur drôle amuse celui qui l'a écrite et
 * personne d'autre : quand on tombe dessus, on cherche où aller. Les liens
 * sont la vraie réponse.
 */
export default function Introuvable() {
  return (
    <section className="section section--tete">
      <div className="conteneur conteneur--texte">
        <p className="surtitre">Erreur 404</p>
        <h1 className="titre-page">Cette page n&apos;existe pas</h1>
        <Trait />
        <p className="chapo">
          Le lien est peut-être ancien, ou mal recopié.
        </p>
        <p className="article__nav">
          <Link className="btn btn--plein" href="/">
            Retour à l&apos;accueil
          </Link>
        </p>
      </div>
    </section>
  );
}
