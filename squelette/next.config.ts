import type { NextConfig } from "next";

/**
 * L'EXPORT STATIQUE.
 *
 * `next build` écrit un site complet dans `out/`, que n'importe quel hébergeur
 * sait servir. En échange, Next désactive tout ce qui suppose un serveur :
 * `headers()`, `revalidate`, les Server Actions, l'optimiseur d'images et le
 * proxy. Voir SQUELETTE.md pour ce qui remplace chacun.
 */
const nextConfig: NextConfig = {
  output: "export",

  /**
   * Chaque page devient un `index.html` dans son dossier, et les adresses
   * finissent par « / ». C'est la seule forme que tous les hébergeurs
   * statiques servent sans réglage particulier.
   */
  trailingSlash: true,

  images: {
    /**
     * L'optimiseur d'images tourne sur un serveur, qui n'existe pas ici.
     * Les images sont donc redimensionnées et converties AVANT le build, par
     * `utils/images.py` : déterministe, et gratuit en jetons.
     */
    unoptimized: true,
  },

  /**
   * ⚠️ LES EN-TÊTES DE SÉCURITÉ NE SONT PAS ICI. `headers()` est sans effet en
   * export statique : Next n'a aucun serveur pour les poser. Ils sont écrits
   * par `utils/securite.py` dans le fichier que réclame l'hébergeur
   * (`_headers`, `netlify.toml`, `.htaccess`). Les mettre ici donnerait une
   * construction verte et un site sans protection.
   */
};

export default nextConfig;
