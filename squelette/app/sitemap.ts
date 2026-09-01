import type { MetadataRoute } from "next";
import { adressesDuSite } from "@/lib/data/plan";
import { ADRESSE_DU_SITE } from "@/lib/site";

/**
 * LE PLAN DU SITE, engendré par Next à /sitemap.xml.
 *
 * Il se construit depuis `lib/data/`, jamais depuis une liste écrite à la
 * main : une liste à tenir à jour finit toujours par oublier les dernières
 * pages, et les moteurs ne les voient jamais.
 */
/**
 * `force-static` est OBLIGATOIRE dès que le plan est `async` : sans lui, Next
 * classe la route comme dynamique et refuse de construire en export statique.
 * Le message d'erreur ne dit pas où l'ajouter.
 */
export const dynamic = "force-static";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const adresses = await adressesDuSite();

  return adresses.map((adresse) => ({
    url: `${ADRESSE_DU_SITE}${adresse.chemin}`,
    lastModified: adresse.modifiee ? new Date(adresse.modifiee) : undefined,
  }));
}
