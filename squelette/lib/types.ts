/**
 * LE CONTRAT ENTRE LES DONNÉES ET LE CODE. Livré vide : le crew le remplit.
 *
 * Un type décrit ici a la même forme qu'il vienne d'un fichier local ou, plus
 * tard, de PostgreSQL. C'est ce qui rend le branchement d'une base mécanique.
 *
 * QUATRE RÈGLES POUR CHAQUE TYPE AJOUTÉ ICI :
 *
 *   1. Les champs de base d'abord : `id`, `slug` (unique), `en_ligne`,
 *      `cree_le`, `modifie_le`. Les dates en ISO, sous forme de `string`.
 *   2. Un champ facultatif est `string | null`, jamais `undefined` ni chaîne
 *      vide : PostgreSQL y mettra NULL, et une divergence ici est un refactor
 *      plus tard.
 *   3. Aucun état dérivé. « en cours », « terminé » se calculent à l'affichage
 *      depuis les dates (voir lib/dates.ts). La donnée ne stocke que des faits.
 *   4. Une liste fermée de valeurs se type par l'union (`"a" | "b"`), pas par
 *      `string` : la contrainte de la future table, recopiée ici.
 */

export {};
