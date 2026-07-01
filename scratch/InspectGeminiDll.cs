using System;
using System.Reflection;
using System.Linq;

public class Program
{
    public static void Main()
    {
        try
        {
            var assembly = Assembly.LoadFrom(@"C:\Users\d.batsilis\source\repos\dimitrisbatsi\GeminiBridge\GeminiBridge\libs\Countersoft.Gemini.Api.dll");
            Console.WriteLine("Loaded Assembly: " + assembly.FullName);
            
            var type = assembly.GetTypes().FirstOrDefault(t => t.Name.EndsWith("ItemService") || t.Name.Contains("Item"));
            if (type == null)
            {
                Console.WriteLine("Could not find ItemService type. Available types:");
                foreach (var t in assembly.GetTypes().Take(20))
                {
                    Console.WriteLine("  " + t.FullName);
                }
                return;
            }
            
            Console.WriteLine("Found Type: " + type.FullName);
            
            var methods = type.GetMethods().Where(m => m.Name == "CustomFieldDataUpdate");
            if (!methods.Any())
            {
                Console.WriteLine("Could not find CustomFieldDataUpdate method. Available methods:");
                foreach (var m in type.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static))
                {
                    Console.WriteLine("  " + m.Name);
                }
                return;
            }
            
            Console.WriteLine("Searching for endpoint constants...");
            foreach (var t in assembly.GetTypes())
            {
                try
                {
                    foreach (var f in t.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance))
                    {
                        if (f.FieldType == typeof(string))
                        {
                            // Static fields only for GetValue(null)
                            if (f.IsStatic)
                            {
                                var val = f.GetValue(null) as string;
                                if (val != null && (val.Contains("customfields") || val.Contains("customfield") || val.Contains("items")))
                                {
                                    Console.WriteLine("  " + t.FullName + "." + f.Name + " = " + val);
                                }
                            }
                        }
                    }
                }
                catch {}
            }


        }
        catch (Exception ex)
        {
            Console.WriteLine("Error: " + ex.ToString());
        }
    }
}
