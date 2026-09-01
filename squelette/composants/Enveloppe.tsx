import type { ReactNode } from "react";
import Link from "next/link";
import { SITE } from "@/site.config";
import { Comportements } from "./Comportements";

/**
 * L'ENVELOPPE : lien d'évitement, en-tête, contenu, pied de page.
 *
 * POURQUOI CE N'EST PAS DIRECTEMENT LE LAYOUT. Une adresse qui ne correspond à
 * rien (la page 404) n'appartient à aucun groupe de routes : Next la rend dans
 * le layout racine. Sans cette extraction, le visiteur perdu tomberait sur un
 * texte nu, sans menu, donc sans moyen de repartir. C'est exactement le moment
 * où la navigation compte le plus.
 *
 * Rien n'est écrit en dur ici : tout vient de site.config.ts.
 */
export function Enveloppe({ children }: { children: ReactNode }) {
  return (
    <>
      {/* Les polices sont servies depuis CE domaine, jamais depuis Google, qui
          recevrait l'adresse IP de chaque visiteur sans son consentement.
          Le fichier est engendré par utils/polices.py. */}
      {/* eslint-disable-next-line @next/next/no-css-tags */}
      <link rel="stylesheet" href="/polices/polices.css" />

      <Comportements />

      <a className="lien-evitement" href="#contenu">
        Aller au contenu
      </a>

      <header className="entete" id="entete">
        <div className="conteneur entete__interieur">
          <Link className="marque" href="/">
            {SITE.nom}
          </Link>

          <nav className="nav" aria-label="Navigation principale">
            {SITE.menu.map((entree) => (
              <Link key={entree.href} href={entree.href}>
                {entree.libelle}
              </Link>
            ))}
          </nav>

          <a className="entete__ecrire" href={`mailto:${SITE.courriel}`}>
            Nous écrire
          </a>
        </div>
      </header>

      <main id="contenu">{children}</main>

      <footer className="pied">
        <div className="conteneur pied__interieur">
          <div>
            <p className="pied__marque">{SITE.nom}</p>
            {SITE.mentions.adresse && <p>{SITE.mentions.adresse}</p>}
          </div>
          <ul className="pied__liens">
            <li>
              <a href={`mailto:${SITE.courriel}`}>{SITE.courriel}</a>
            </li>
            <li>
              <Link href="/mentions-legales">Mentions légales</Link>
            </li>
          </ul>
        </div>
      </footer>
    </>
  );
}
