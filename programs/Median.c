#include <stdio.h>
#include <assert.h>

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

     printf("Middle number is: %d\n",m);
     return m;     
}

int main(int argc, char* argv[]){
     int rv = correctQ(atoi(argv[1]), atoi(argv[2]), atoi(argv[3]));
     return 0;
}

