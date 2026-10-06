import "./commission.css";

import { ContractList } from "./ContractList";
import { ContractPage } from "./ContractPage";
import { ImportPage } from "./ImportPage";
import { useNav } from "./shared";

/** The commission configurator: contracts, their terms and amendments, and the
 *  workbook import. Unlike the other dashboards it writes data, through
 *  /api/modules/commission. Screens are chosen by search params:
 *  ?view=import, ?c=<contract id>&tab=<tab>, or neither for the list. */
export function Commission(_: { slug: string }) {
  const { params } = useNav();
  if (params.get("view") === "import") return <ImportPage />;
  const id = Number(params.get("c"));
  if (id) return <ContractPage key={id} id={id} />;
  return <ContractList />;
}
