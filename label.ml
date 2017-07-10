open Cil
module A = Array				             
module E = Errormsg
module H = Hashtbl
module P = Printf	     
module L = List
module CM = Common	     
	      
class labelVisitor
	(sid:int) =  
object
  inherit nopCilVisitor
  method vstmt (s:stmt) =
    let action (s:stmt): stmt =
      if s.sid = sid then (
	s.labels <- [Label("suspstmt" ^ (string_of_int s.sid), !currentLoc, false)]
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
    let sid:CM.sid_t = int_of_string Sys.argv.(2) in
    let labelSrc:string = Sys.argv.(3) in 

    let ast, mainFd'', mainQFd'', correctQFd'', stmtHt = CM.read_file_bin astFile in

    visitCilFileSameGlobals ((new labelVisitor) sid) ast;
    
    E.log "Add label to stmt %d\n" sid;
    CM.writeSrc labelSrc ast
end
