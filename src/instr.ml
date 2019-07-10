open Cil
module E = Errormsg
module H = Hashtbl
module P = Printf	     
module L = List
module CM = Common	     
				      
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
