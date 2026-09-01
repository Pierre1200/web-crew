"use client";

import { useSyncExternalStore } from "react";
import { etat } from "@/lib/dates";

/**
 * L'ÉTAT D'UNE PÉRIODE : « En cours », « Bientôt », « Terminé ».
 *
 * POURQUOI CE COMPOSANT EXISTE, et c'est le piège numéro un de l'export
 * statique. Le site est construit une fois, puis servi tel quel. Un état
 * calculé pendant le rendu d'une page serait donc figé AU JOUR DU BUILD : un
 * site construit en juillet afficherait encore « En cours » en septembre.
 * ESLint, TypeScript et `next build` passeraient tous les trois, et la capture
 * visuelle, faite le jour même, ne verrait rien.
 *
 * Le calcul est donc refait dans le navigateur, à chaque visite.
 */

// « Sommes-nous dans le navigateur ? », posé comme une source extérieure à
// React. Au build la réponse est non, après l'hydratation elle est oui.
//
// POURQUOI PAS un useEffect qui pose un état : React interdit désormais
// d'appeler setState directement dans un effet (rendus en cascade), et ESLint
// le refuse. POURQUOI PAS un calcul direct au rendu : la valeur du build et
// celle du visiteur diffèrent, et React rejette une hydratation qui ne
// correspond pas.
//
// Rien ne change jamais après le montage, donc l'abonnement ne fait rien.
const RIEN = () => () => {};
const DANS_LE_NAVIGATEUR = () => true;
const PENDANT_LA_CONSTRUCTION = () => false;

export function Etat({ debut, fin }: { debut: string; fin: string }) {
  const monte = useSyncExternalStore(
    RIEN,
    DANS_LE_NAVIGATEUR,
    PENDANT_LA_CONSTRUCTION,
  );

  // Rien au premier rendu : le balisage servi est donc le même que celui
  // attendu par React, et l'état apparaît juste après.
  if (!monte) return null;

  const situation = etat(debut, fin);
  if (!situation) return null;

  return (
    <span className={`etat etat--${situation.classe}`}>{situation.libelle}</span>
  );
}
