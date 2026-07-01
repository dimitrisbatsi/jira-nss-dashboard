using System;
using System.Reflection;
using Countersoft.Gemini.Api;
using Countersoft.Gemini.Commons.Entity;

public class Program
{
    static Program()
    {
        AppDomain.CurrentDomain.AssemblyResolve += (sender, args) =>
        {
            string folderPath = @"C:\Users\d.batsilis\source\repos\dimitrisbatsi\GeminiBridge\GeminiBridge\libs\";
            string assemblyPath = System.IO.Path.Combine(folderPath, new AssemblyName(args.Name).Name + ".dll");
            if (System.IO.File.Exists(assemblyPath)) return Assembly.LoadFrom(assemblyPath);
            return null;
        };
    }

    public static void Main()
    {
        try
        {
            Console.WriteLine("Initializing ServiceManager...");
            ServiceManager manager = new ServiceManager("https://gemini.epsilonnet.gr/", "apiUser", string.Empty, "fyrqc7c3i7");
            
            Console.WriteLine("Updating custom field via SDK...");
            var customFieldData = new CustomFieldData
            {
                CustomFieldId = 1082,
                Data = "PYLMIG-1062",
                IssueId = 418609,
                ProjectId = 81,
                UserId = 5031
            };
            
            var result = manager.Item.CustomFieldDataUpdate(customFieldData);
            Console.WriteLine("Success! Result returned: " + (result != null ? "Not null" : "Null"));
        }

        catch (Exception ex)
        {
            Console.WriteLine("SDK Update Failed: " + ex.ToString());
        }
    }
}
