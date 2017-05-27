#include <stdio.h>
#include <assert.h>
#include <stdlib.h>

int buggyQ(int x, int y, int z) {
     int m = z;
     if (y < z){
	  if (x<y){
	       m = y;
	  }
	  else {
	       if (x<z){
		    m = y; //BUG, should be m = x
	       }
	  }
     }
     else{
	  if(x>y){
	       m=y;
	  }
	  else {
	       if (x>z){
		    m =x;
	       }
	  }
     }

     return m ;
}


int correctQ(int x, int y, int z){
     int m = z;
     if (y < z){
	  if (x<y){
	       m = y;
	  }
	  else {
	       if (x<z){
		    m = x;
	       }
	  }
     }
     else{
	  if(x>y){
	       m=y;
	  }
	  else {
	       if (x>z){
		    m =x;
	       }
	  }
     }
     return m;     
}


int mainQ(int x, int y, int z){
     int rb = buggyQ(x,y,z);
     int rc = correctQ(x, y, z);
     
     if (rb == rc){
     	  printf("PASS (rb = rc = %d) with input: x %d, y %d, z %d\n",
     		 rc, x, y, z);
	  return 1;
     }
     else{
     	  printf("FAIL (rb %d, rc %d) with input: x %d, y %d, z %d\n",
     		 rb, rc, x, y, z);
	  return 0;
     }
}

int main(int argc, char* argv[]){
     mainQ(atoi(argv[1]), atoi(argv[2]), atoi(argv[3]));
     return 0;
}

