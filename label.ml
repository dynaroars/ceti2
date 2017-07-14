open Cil
module A = Array				             
module E = Errormsg
module H = Hashtbl
module P = Printf	     
module L = List
module CM = Common	     

module SS =
  Set.Make(struct
	    type t = CM.sid_t
	    let compare = Pervasives.compare
	  end)
	  
class labelVisitor (sids:SS.t) =  
object
  inherit nopCilVisitor
  method vstmt (s:stmt) =
    let action (s:stmt): stmt =
      if SS.mem s.sid sids then (
	s.labels <- [Label("repairStmt" ^ (string_of_int s.sid), !currentLoc, false)]
      ); s
    in
    ChangeDoChildrenPost(s, action)
  end

	  

(* main *)
(*Example:  ./label.exe /var/tmp/CETI2_XhtAbh/MedianBad1.c.ast 13 /var/tmp/CETI2_XhtAbh/MedianBad1.label.s13.c
Output:(2, 3, 4); (13, 3, 4); (3, 2, 1); (3, 3, 4)  (sid, cid, idx)*)
let () = begin
    initCIL();
    Cil.lineDirectiveStyle:= None; (*reduce code, remove all junk stuff*)
    Cprint.printLn := false; (*don't print line #*)
    (* for Cil to retain &&, ||, ?: instead of transforming them to If stmts *)
    Cil.useLogicalOperators := true;
    
    let astFile:string = Sys.argv.(1) in
    let sids:CM.sid_t list = L.map int_of_string (CM.str_split Sys.argv.(2)) in
    let labelSrc:string = Sys.argv.(3) in
    
    let ast, mainFd'', mainQFd'', correctQFd'', stmtHt = CM.read_file_bin astFile in
    let sids:SS.t = List.fold_right SS.add sids SS.empty in
    visitCilFileSameGlobals ((new labelVisitor) sids) ast;
    P.printf "Add labels to %d stmt\n" (SS.cardinal sids);
    CM.writeSrc labelSrc ast
end
