"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

/**
 * LES COMPORTEMENTS DU SITE : le témoin `data-js`, les apparitions au
 * défilement, et l'état de l'en-tête une fois le haut de page dépassé.
 *
 * Les trois partagent la même question (« où en est le défilement ? ») et le
 * même cycle de vie : un seul composant, un seul jeu d'observateurs.
 */
export function Comportements() {
  /**
   * POURQUOI LE CHEMIN EST UNE DÉPENDANCE, et c'est le cœur du fichier.
   *
   * Ce composant vit dans l'enveloppe : il RESTE MONTÉ d'une page à l'autre.
   * Avec un tableau de dépendances vide, l'effet ne jouerait qu'au premier
   * chargement. En arrivant sur une autre page par un lien, on aurait alors
   * `data-js` toujours posé, donc le CSS cachant toujours les blocs, mais plus
   * personne pour les révéler : une page entière invisible, occupant sa place.
   *
   * Et le bug ne se voit pas en développement, où l'on recharge sans arrêt :
   * un rechargement remonte le composant et répare tout.
   */
  const chemin = usePathname();

  useEffect(() => {
    const racine = document.documentElement;
    const aReveler = document.querySelectorAll<HTMLElement>("[data-reveal]");

    // Le réglage système « réduire les animations » n'est pas décoratif.
    const mouvementReduit = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Ce qui est DÉJÀ à l'écran est marqué visible AVANT de poser le témoin :
    // sinon le haut de la page s'affiche, disparaît le temps d'une image, puis
    // revient. L'observateur, lui, ne répond jamais dans la même image.
    if (!mouvementReduit) {
      for (const bloc of aReveler) {
        const boite = bloc.getBoundingClientRect();
        if (boite.top < window.innerHeight * 0.88 && boite.bottom > 0) {
          bloc.setAttribute("data-visible", "true");
        }
      }
    }

    // Le CSS ne cache les blocs QUE si ce témoin est présent. Il est posé ici,
    // donc seulement si le JavaScript a bien chargé : en cas d'échec, tout
    // reste visible au lieu de disparaître.
    racine.dataset.js = "1";

    if (mouvementReduit || !("IntersectionObserver" in window)) {
      aReveler.forEach((bloc) => bloc.setAttribute("data-visible", "true"));
      return;
    }

    const observateur = new IntersectionObserver(
      (entrees) => {
        for (const entree of entrees) {
          if (!entree.isIntersecting) continue;
          entree.target.setAttribute("data-visible", "true");
          // On cesse d'observer : l'effet ne se rejoue pas si l'on remonte,
          // ce qui deviendrait vite agaçant.
          observateur.unobserve(entree.target);
        }
      },
      // 12 % de marge négative en bas : l'apparition démarre quand le bloc est
      // bien entré dans l'écran, pas dès qu'il en effleure le bord.
      { threshold: 0.1, rootMargin: "0px 0px -12% 0px" },
    );
    aReveler.forEach((bloc) => {
      if (bloc.getAttribute("data-visible") !== "true") observateur.observe(bloc);
    });

    // Une sentinelle invisible en haut de page plutôt qu'une écoute de
    // l'événement scroll : le navigateur s'en charge sans ralentir le
    // défilement.
    const sentinelle = document.createElement("div");
    sentinelle.style.cssText =
      "position:absolute;top:0;left:0;width:1px;height:70vh;pointer-events:none;";
    document.body.insertBefore(sentinelle, document.body.firstChild);

    const entete = document.getElementById("entete");
    const veilleur = new IntersectionObserver(([entree]) => {
      entete?.setAttribute("data-defile", entree.isIntersecting ? "false" : "true");
    });
    veilleur.observe(sentinelle);

    /**
     * LE FILET DE SÉCURITÉ. `data-js` est un contrat : « je cache les blocs et
     * je promets de les révéler ». Tout ce qui empêche d'en tenir la seconde
     * moitié laisse du contenu invisible À VIE, sans message d'erreur.
     * Après 2,5 s, un bloc dans le champ de vision aurait dû apparaître depuis
     * longtemps : s'il est encore caché, personne ne viendra le chercher.
     */
    const filet = window.setTimeout(() => {
      for (const bloc of aReveler) {
        if (bloc.getAttribute("data-visible") === "true") continue;
        if (bloc.getBoundingClientRect().top < window.innerHeight) {
          bloc.setAttribute("data-visible", "true");
        }
      }
    }, 2500);

    return () => {
      window.clearTimeout(filet);
      observateur.disconnect();
      veilleur.disconnect();
      sentinelle.remove();
    };
  }, [chemin]);

  return null;
}
