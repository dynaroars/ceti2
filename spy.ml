open Cil
module A = Array				             
module E = Errormsg
module H = Hashtbl
module P = Printf	     
module L = List
module CM = Common	     
module MT = Modtemplate
	      
let spy 
      (filename:string)
      (stmtHt:(int,stmt*fundec) H.t)
      (sid:CM.sid_t)
      (tplLevel:int)
      (maxV:int)
    : MT.spy_t list
  = 
  let s, fd = H.find stmtHt sid in
  E.log "Spying stmt id %d in fun %s\n%a\n" sid fd.svar.vname dn_stmt s;
  
  match s.skind with 
  |Instr ins ->
    assert (L.length ins = 1);
    let spyf p c = if p then c#spyStmt filename sid fd (L.hd ins) else None in 
    let rs = L.map(fun c -> spyf (c#cid <= tplLevel) c) MT.tplCls in
    CM.list_of_some rs
  |_ -> E.log "no info obtained on stmt %d\n%a" sid dn_stmt s; []


(* main *)
(*Example:  ./spy.exe /var/tmp/CETI2_XhtAbh/MedianBad1.c.ast "2 13 3" 4 1000
Output:(2, 3, 4); (13, 3, 4); (3, 2, 1); (3, 3, 4)  (sid, cid, idx)*)
let () = begin
    initCIL();
    Cil.lineDirectiveStyle:= None; (*reduce code, remove all junk stuff*)
    Cprint.printLn := false; (*don't print line #*)
    (* for Cil to retain &&, ||, ?: instead of transforming them to If stmts *)
    Cil.useLogicalOperators := true;
    
    let astFile:string = Sys.argv.(1) in
    let sids:CM.sid_t list = L.map int_of_string (CM.str_split Sys.argv.(2)) in
    let tplLevel:int = int_of_string Sys.argv.(3) in
    let maxV:int = int_of_string Sys.argv.(4) in

    let ast, mainFd'', mainQFd'', correctQFd'', stmtHt = CM.read_file_bin astFile in
    let rs = L.map (fun sid -> spy ast.fileName stmtHt sid tplLevel maxV) sids in
    let rs' = L.filter (function |[] -> false |_ -> true) rs in
    let rs = L.flatten rs' in
    E.log "Spy: Got %d info from %d sids" (L.length rs) (L.length rs');
    if (L.length rs) = 0 then (E.log "No spied info. Exit!"; exit 0);
    let rs = L.map MT.string_of_spys rs in
    P.printf "%s" (String.concat "; " rs)
    
end
