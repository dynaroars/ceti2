open Cil
module H = Hashtbl
module P = Printf	     
module L = List
module CM = Common	     
				      

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
    let stderrVi = CM.mkVi ~ftype:(TPtr(TVoid [], [])) "_coverage_fout" in
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
	f.sbody.bstmts <- self#create_fprintf_stmt 0 :: f.sbody.bstmts
      );
      f
    in
    ChangeDoChildrenPost(f, action)
end
			  
(* main *)			   
let () = begin
    initCIL();
    Cil.lineDirectiveStyle:= None; (*reduce code, remove all junk stuff*)
    Cprint.printLn := false; (*don't print line #*)
    (* for Cil to retain &&, ||, ?: instead of transforming them to If stmts *)
    Cil.useLogicalOperators := true;
    

    let flSrc:string = Sys.argv.(1) in (*save to this file*)
    let astFile:string = Sys.argv.(2) in    
    let ast, mainQFd, mainFd = CM.read_file_bin astFile in

    (* transform *)
    
    
    (* add include "klee/klee.h" to file *)
    ast.globals <- (GText "#include \"klee/klee.h\"") :: ast.globals;

    CM.writeSrc flSrc ast
end
