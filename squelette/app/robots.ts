import type { MetadataRoute } from "next";
import { ADRESSE_DU_SITE } from "@/lib/site";

/**
 * Le robots.txt, engendré par Next à /robots.txt.
 * Il dit ce que les moteurs peuvent parcourir, et où trouver le plan du site.
 */
// Comme le plan du site : sans `force-static`, Next classe la route comme
// dynamique et refuse de construire en export statique.
export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${ADRESSE_DU_SITE}/sitemap.xml`,
  };
}
