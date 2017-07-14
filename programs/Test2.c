#include <stdio.h>
#include <assert.h>
#include <stdlib.h>

int buggyQ(int x) {
     return x <= 50 ;
}


int correctQ(int x){
     return x == 100;     
}


int mainQ(int x){
     int rb = buggyQ(x);
     int rc = correctQ(x);
     
     if (rb == rc){
     	  printf("PASS (rb = rc = %d) with input: x %d\n",
     		 rc, x);
	  return 1;
     }
     else{
     	  printf("FAIL (rb %d, rc %d) with input: x %d\n",
     		 rb, rc, x);
	  return 0;
     }
}

void main(int argc, char* argv[]){
     mainQ(atoi(argv[1]));
}

