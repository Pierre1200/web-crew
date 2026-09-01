import { EnteteSection } from "@/composants/Trait";
import { SITE } from "@/site.config";

/**
 * L'ACCUEIL. REMPLACÉE PAR LE CREW.
 *
 * Elle n'est là que pour que le squelette construise et se serve tel quel :
 * un squelette qu'on ne peut pas lancer ne prouve rien.
 */
export default function Accueil() {
  return (
    <section className="section section--tete">
      <div className="conteneur conteneur--texte">
        <h1 className="titre-page">{SITE.nom}</h1>
        <EnteteSection surtitre="Squelette" titre="Le site n'a pas encore de contenu">
          {SITE.accroche}
        </EnteteSection>
      </div>
    </section>
  );
}
