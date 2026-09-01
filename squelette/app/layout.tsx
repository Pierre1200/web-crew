import type { Metadata } from "next";
import { SITE } from "@/site.config";
import { ADRESSE_DU_SITE } from "@/lib/site";
import { Enveloppe } from "@/composants/Enveloppe";

/**
 * L'ENVELOPPE DE TOUT LE SITE.
 *
 * `lang="fr"` n'est pas cosmétique : c'est ce qui dit aux lecteurs d'écran de
 * prononcer la page en français, et aux navigateurs quelle césure appliquer.
 *
 * PAS DE GROUPE DE ROUTES ICI, contrairement à un site qui aurait une
 * administration : il n'y a qu'un seul public, donc une seule enveloppe. Elle
 * est posée dès la racine, ce qui donne à la page 404 son en-tête et son menu
 * sans rien faire de plus.
 */

// L'ORDRE DE CES QUATRE IMPORTS EST LE FONCTIONNEMENT MÊME DE LA CHARTE.
// base : invariant. charte : les valeurs. composants : engendré.
// correctifs : dernier, c'est là et NULLE PART AILLEURS que la boucle de
// correction visuelle a le droit d'écrire.
import "./base.css";
import "./charte.css";
import "./composants.css";
import "./correctifs.css";

export const metadata: Metadata = {
  /**
   * `metadataBase` dit à Next comment transformer un chemin relatif en adresse
   * entière. Sans elle, l'image de partage serait annoncée comme « /assets/… »,
   * que le service affichant l'aperçu ne sait pas résoudre : aperçu sans image.
   */
  metadataBase: new URL(ADRESSE_DU_SITE),
  title: SITE.nom,
  description: SITE.description,
  openGraph: {
    type: "website",
    locale: "fr_FR",
    siteName: SITE.nom,
    title: SITE.nom,
    description: SITE.description,
    url: "/",
    images: [
      {
        url: SITE.partage.chemin,
        width: SITE.partage.largeur,
        height: SITE.partage.hauteur,
        alt: SITE.partage.alt,
      },
    ],
  },
};

export default function LayoutRacine({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body>
        <Enveloppe>{children}</Enveloppe>
      </body>
    </html>
  );
}
