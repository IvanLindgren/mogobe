import com.jpexs.decompiler.flash.SWF;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Remap every walking character and reference without editing original files. */
public class MergeItemAnimations {
  public static void main(String[] args) throws Exception {
    Path source=Path.of(args[0]), output=Path.of(args[1]);
    Files.createDirectories(output);
    int count=0;
    try (var paths=Files.list(source.resolve("Walking"))) {
      for (Path walking: paths.filter(p->p.toString().endsWith(".swf")).sorted().toList()) {
        Path standing=source.resolve("InUse").resolve(walking.getFileName());
        if (!Files.exists(standing)) continue;
        SWF a,b;
        try(var in=Files.newInputStream(standing)){a=new SWF(in,false);}
        try(var in=Files.newInputStream(walking)){b=new SWF(in,false);}
        int offset=a.getNextCharacterId();
        var ids=new ArrayList<Integer>(b.getCharacters(false).keySet());
        ids.sort(Collections.reverseOrder());
        for(int id:ids) b.replaceCharacter(id,id+offset);
        try(var out=Files.newOutputStream(output.resolve(walking.getFileName()))){b.saveTo(out);}
        Files.writeString(output.resolve(walking.getFileName()+".offset"),String.valueOf(offset));
        if(++count%200==0) System.out.println(count);
      }
    }
    System.out.println("Remapped "+count+" walking animations");
  }
}
