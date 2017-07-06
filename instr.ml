open Cil
module E = Errormsg
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

let mkMain mainFd mainQFd maxV =
  let uks = L.mapi(fun i vi ->
		  let v, i = CM.mkUk i vi.vtype (-1*maxV) maxV mainFd in 
		  CM.exp_of_vi v, i
		  ) mainQFd.sformals in

  let args, instrs = L.split uks in
  let instrs = L.flatten instrs in 
  let stmt1:stmtkind = Instr(instrs) in

  let mainQTyp:typ = match mainQFd.svar.vtype with 
    |TFun(t,_,_,_) -> t
    |_ -> E.s(E.error "%s is not fun typ %a\n" 
		      mainQFd.svar.vname d_type mainQFd.svar.vtype)
  in

  (*mainQTyp temp;*)
  let tmp:lval = var(makeTempVar mainFd mainQTyp) in 
  let icall = CM.mkCall ~ftype:mainQTyp ~av:(Some tmp) "mainQ" args in
  let stmt2:stmtkind = Instr([icall]) in
  
  let stmts = [mkStmt stmt1 ; mkStmt stmt2] in  
  mainFd.sbody.bstmts <- stmts
			  
(* main *)			   
let () = begin
    initCIL();
    Cil.lineDirectiveStyle:= None; (*reduce code, remove all junk stuff*)
    Cprint.printLn := false; (*don't print line #*)
    (* for Cil to retain &&, ||, ?: instead of transforming them to If stmts *)
    Cil.useLogicalOperators := true;
    
    let flSrc:string = Sys.argv.(1) in (*save to this file*)
    let astFile:string = Sys.argv.(2) in
    let maxV:int = int_of_string Sys.argv.(3) in
    let ast, mainFd, mainQFd, correctQFd'', stmtHt = CM.read_file_bin astFile in

    (* transform *)
    mkMain mainFd mainQFd maxV;
    
    (* add include "klee/klee.h" to file *)
    ast.globals <- (GText "#include \"klee/klee.h\"") :: ast.globals;

    CM.writeSrc flSrc ast
end
