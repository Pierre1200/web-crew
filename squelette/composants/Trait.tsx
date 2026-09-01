import type { ReactNode } from "react";

/**
 * LE TRAIT SOUS LES TITRES.
 *
 * Une bordure CSS serait parfaitement droite : elle aurait l'air imprimée par
 * une machine. Celui-ci ondule légèrement. `preserveAspectRatio="none"`
 * autorise l'étirement horizontal, donc le même dessin sert à toutes les
 * largeurs. `aria-hidden` : c'est une décoration, pas une information.
 */
export function Trait() {
  return (
    <svg className="trait" viewBox="0 0 120 10" preserveAspectRatio="none" aria-hidden="true">
      <path
        d="M2 6.5C18 3.2 34 2.4 52 3.6c17 1.1 33 3.2 50 1.4C110 4.4 115 3.6 118 2.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        opacity="0.85"
      />
    </svg>
  );
}

/**
 * L'en-tête d'une section : surtitre, titre, trait, chapô facultatif.
 * Toujours la même structure, donc un seul composant plutôt que six copies.
 */
export function EnteteSection({
  surtitre,
  titre,
  ident,
  children,
}: {
  surtitre: string;
  titre: ReactNode;
  ident?: string;
  children?: ReactNode;
}) {
  return (
    <div className="entete-section">
      <p className="surtitre">{surtitre}</p>
      <h2 id={ident}>{titre}</h2>
      <Trait />
      {children && <p className="chapo">{children}</p>}
    </div>
  );
}
