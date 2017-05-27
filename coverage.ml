(*instrument printf stmts to C file*)

open Cil
module E = Errormsg       
module H = Hashtbl
module P = Printf	     
module L = List
module CM = Common	     
				      
let stderrVi = CM.mkVi ~ftype:(TPtr(TVoid [], [])) "_coverage_fout"
(*
  walks over AST and preceeds each stmt with a printf that writes out its sid
  create a stmt consisting of 2 Call instructions
  fprintf "_coverage_fout, sid"; 
  fflush();
 *)
      
class coverageVisitor = object(self)
  inherit nopCilVisitor

  method private create_fprintf_stmt (sid : CM.sid_t) :stmt = 
  let str = P.sprintf "%d\n" sid in
  let stderr = CM.expOfVi stderrVi in
  let instr1 = CM.mkCall "fprintf" [stderr; Const (CStr(str))] in 
  let instr2 = CM.mkCall "fflush" [stderr] in
  mkStmt (Instr([instr1; instr2]))
    
  method vblock b = 
    let action (b: block) :block= 
      let insert_printf (s: stmt): stmt list = 
	if s.sid > 0 then [self#create_fprintf_stmt s.sid; s]
	else [s]
      in
      let stmts = L.map insert_printf b.bstmts in 
      {b with bstmts = L.flatten stmts}
    in
    ChangeDoChildrenPost(b, action)
      
  method vfunc f = 
    let action (f: fundec) :fundec = 
      (*print 0 when entering main so we know it's a new run*)
      if f.svar.vname = "main" then (
	f.sbody.bstmts <- [self#create_fprintf_stmt 0] @ f.sbody.bstmts
      );
      f
    in
    ChangeDoChildrenPost(f, action)
end
			  
(* main *)			   
let () = begin
    E.colorFlag := true;

    let src = Sys.argv.(1) in
    let covSrc = Sys.argv.(2) in 
    initCIL();
    Cil.lineDirectiveStyle:= None;  (*reduce code, remove all junk stuff*)

    let ast = Frontc.parse src () in

    (* (\*save orig file*\) *)
    (* let origSrc = src ^ ".cil.c"in *)
    (* writeSrc origSrc ast; *)

    visitCilFileSameGlobals (new CM.everyVisitor) ast;
    visitCilFileSameGlobals (new CM.breakCondVisitor :> cilVisitor) ast;

    (*add stmt id*)
    let stmtHt = H.create 1024 in
    visitCilFileSameGlobals (new CM.numVisitor stmtHt :> cilVisitor) ast;
    
    (*add printf stmts*)
    visitCilFileSameGlobals (new coverageVisitor) ast;

    (*add to global
    _coverage_fout = fopen("file.c.path", "ab");
     *)

    let newGlobal = GVarDecl(stderrVi, !currentLoc) in 
    ast.globals <- newGlobal::ast.globals;

    let pathFile = covSrc ^ ".path" in
    
    let lhs = var(stderrVi) in
    let arg1 = Const(CStr(pathFile)) in
    let arg2 = Const(CStr("ab")) in
    let instr = CM.mkCall ~av:(Some lhs) "fopen" [arg1; arg2] in
    let newStmt = mkStmt (Instr[instr]) in
    
    let fd = getGlobInit ast in
    fd.sbody.bstmts <- newStmt::fd.sbody.bstmts;
    
    CM.writeSrc covSrc ast
end
